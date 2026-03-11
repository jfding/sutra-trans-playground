"""API client supporting both search APIs and OpenAI-compatible chat completion APIs."""
import os
import json
import sys
import httpx
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any
from dotenv import load_dotenv
from openai import OpenAI

# Load .env file from project root
project_root = Path(__file__).parent
load_dotenv(dotenv_path=project_root / ".env")


class LLMClient:
    """Client for calling LLM APIs, supporting both search APIs and OpenAI-compatible chat APIs."""

    def __init__(
        self,
        api_url: str,
        model: Optional[str] = None,
        api_key_name: Optional[str] = None,
        verbose: bool = False,
        extra_params: Optional[Dict[str, Any]] = None,
        q_key: Optional[str] = None,
        backend: str = "httpx"
    ):
        """
        Initialize API client.

        Args:
            api_url: API endpoint URL (required, from config JSON)
            model: Model name
            api_key_name: Environment variable name for API key (required, from config JSON)
            verbose: If True, print and save HTTP request details
            extra_params: Optional extra parameters dict that will be automatically added to payload
            q_key: Optional key name for question/prompt in request payload. If None, uses OpenAI compatible mode (messages)
            backend: Backend to use for API calls: "httpx" (default) or "openai"
        """
        if not api_url:
            raise ValueError("api_url is required and must be provided from config JSON")

        self.verbose = verbose
        self.api_url = api_url

        # Get API key from specified environment variable
        if not api_key_name:
            raise ValueError("api_key_name is required and must be provided from config JSON")

        self.api_key = os.getenv(api_key_name)

        # Validate API key
        if not self.api_key:
            #raise ValueError(f"API key is required. Set {api_key_name} environment variable.")
            print(f"Warning: API key is required. Set {api_key_name} environment variable.")
            pass

        self.model = model
        self.backend = backend

        # Store extra parameters that will be automatically added to payload
        self.extra_params = extra_params or {}
        
        # Extract proxy_url from extra_params if present (not sent to API)
        self.proxy_url = None
        if 'proxy_url' in self.extra_params:
            proxy_url = self.extra_params.pop('proxy_url')
            if proxy_url:  # Only store non-empty proxy URLs
                self.proxy_url = proxy_url
        
        # If proxy_url not set in config, check environment variable
        if not self.proxy_url and backend == "openai":
            env_proxy = os.getenv("OPENAI_PROXY") or os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY") or os.getenv("ALL_PROXY")
            if env_proxy:
                self.proxy_url = env_proxy
        
        # Log proxy configuration (mask credentials in URL)
        if self.proxy_url and backend == "openai":
            # Basic masking of credentials in proxy URL
            import urllib.parse
            try:
                parsed = urllib.parse.urlparse(self.proxy_url)
                if parsed.username or parsed.password:
                    # Mask credentials
                    netloc = f"{'***' if parsed.username else ''}:{'***' if parsed.password else ''}@{parsed.hostname}"
                    if parsed.port:
                        netloc += f":{parsed.port}"
                    masked_url = urllib.parse.urlunparse(parsed._replace(netloc=netloc))
                    print(f"Using proxy for OpenAI API: {masked_url}", file=sys.stderr)
                else:
                    print(f"Using proxy for OpenAI API: {self.proxy_url}", file=sys.stderr)
            except Exception:
                # If URL parsing fails, print generic message
                print("Using proxy for OpenAI API (URL masked)", file=sys.stderr)

        # Store question key name (if None, means OpenAI compatible mode)
        self.q_key = q_key

        # Initialize OpenAI client if backend is "openai"
        self.openai_client = None
        if self.backend == "openai":
            # Use api_url as base_url if it's not the default OpenAI endpoint
            base_url = None
            if self.api_url and self.api_url != "https://api.openai.com/v1":
                # Heuristic: extract base URL up to /v1 if present
                import re
                match = re.match(r"(https?://[^/]+/v1)/.*", self.api_url)
                if match:
                    base_url = match.group(1)
                else:
                    base_url = self.api_url.rstrip('/')
            # Create HTTP client with proxy if configured
            http_client = None
            if self.proxy_url:
                # Create httpx client with proxy
                http_client = httpx.Client(proxy=self.proxy_url)
            
            self.openai_client = OpenAI(
                api_key=self.api_key, 
                base_url=base_url,
                http_client=http_client
            )

    def _apply_extra_params(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply extra_params to payload.

        Args:
            payload: Base payload dictionary

        Returns:
            Payload with extra_params merged in
        """

        # Apply extra_params to payload
        for key, value in self.extra_params.items():
            if value is None:
                continue  # Skip None values

            # Only add if not already in payload (method arguments take precedence)
            if key not in payload:
                payload[key] = value

        return payload

    def _log_request_details(
        self,
        method: str,
        url: str,
        headers: Dict[str, str],
        payload: Dict[str, Any],
        response: Optional[httpx.Response] = None
    ) -> None:
        """
        Log HTTP request details to stderr and save to file.
        Always logs endpoint and payload, regardless of verbose setting.

        Args:
            method: HTTP method (e.g., "POST")
            url: Request URL
            headers: Request headers (sensitive values will be masked)
            payload: Request payload/body
            response: Optional response object
        """
        # Always log endpoint and payload, even if verbose=False
        response_body_preview = None

        # Mask sensitive headers
        safe_headers = {}
        for key, value in headers.items():
            if key.lower() in ("authorization", "secret-key", "api-key"):
                # Mask the value but keep some info
                if value:
                    parts = value.split()
                    if len(parts) > 1:
                        safe_headers[key] = f"{parts[0]} [MASKED]"
                    else:
                        safe_headers[key] = "[MASKED]"
                else:
                    safe_headers[key] = value
            else:
                safe_headers[key] = value

        # Build log entry
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "request": {
                "method": method,
                "url": url,
                "headers": safe_headers,
                "payload": payload
            }
        }

        if response:
            # Get response body preview
            response_body_preview = "[Response body not available]"
            try:
                # Try to read response body
                response_body = response.text
                if len(response_body) > 1000:
                    response_body_preview = response_body[:1000] + f"\n... (truncated, total length: {len(response_body)} chars)"
                else:
                    response_body_preview = response_body
            except (AttributeError, Exception):
                # If we can't read the body (e.g., it's already been consumed or it's binary)
                pass

            log_entry["response"] = {
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "body_preview": response_body_preview
            }

        # Print to stderr - always log endpoint and payload
        print("\n" + "="*80, file=sys.stderr)
        print("HTTP REQUEST DETAILS", file=sys.stderr)
        print("="*80, file=sys.stderr)
        print(f"Method: {method}", file=sys.stderr)
        print(f"Endpoint: {url}", file=sys.stderr)
        print(f"\nHeaders:", file=sys.stderr)
        for key, value in safe_headers.items():
            print(f"  {key}: {value}", file=sys.stderr)
        print(f"\nPayload:", file=sys.stderr)
        print(json.dumps(payload, indent=2, ensure_ascii=False), file=sys.stderr)

        if response:
            print(f"\nResponse Status: {response.status_code}", file=sys.stderr)
            if self.verbose:
                # Only show detailed response info if verbose
                print(f"Response Headers:", file=sys.stderr)
                for key, value in response.headers.items():
                    print(f"  {key}: {value}", file=sys.stderr)
                print(f"\nResponse Body Preview:", file=sys.stderr)
                assert response_body_preview is not None
                print(response_body_preview, file=sys.stderr)

        print("="*80 + "\n", file=sys.stderr)

        # Save to file only if verbose
        if self.verbose:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_filename = f"http_request_{timestamp}.json"
            log_path = project_root / log_filename

            with open(log_path, "w", encoding="utf-8") as f:
                json.dump(log_entry, f, indent=2, ensure_ascii=False)

            print(f"HTTP request details saved to: {log_filename}", file=sys.stderr)

    def _make_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Make HTTP POST request to API.

        Args:
            payload: Request payload dictionary (should already have extra_params applied)

        Returns:
            API response as dictionary
        """
        if self.backend == "openai":
            # Use OpenAI SDK
            cclient = OpenAI()
            resp = cclient.responses.create(
                    model="gpt-5.2",
                    input=payload['messages']
                    )
            print(resp.output_text)
            return resp.output_text






            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            # Log request details before sending (always log endpoint and payload)
            self._log_request_details("POST", self.api_url, headers, payload, None)
            
            # Prepare parameters for OpenAI SDK
            # Remove stream if present (non-streaming request)
            payload = {k: v for k, v in payload.items() if k != "stream"}
            # Call OpenAI SDK
            assert self.openai_client is not None
            response = self.openai_client.chat.completions.create(**payload)
            # Convert response to dict
            result = response.model_dump()
            
            # Log response status if verbose
            if self.verbose:
                print(f"\nResponse Status: 200", file=sys.stderr)
                try:
                    response_body = json.dumps(result, ensure_ascii=False)
                    if len(response_body) > 1000:
                        response_body_preview = response_body[:1000] + f"\n... (truncated, total length: {len(response_body)} chars)"
                    else:
                        response_body_preview = response_body
                    print(f"Response Body Preview:", file=sys.stderr)
                    assert response_body_preview is not None
                    print(response_body_preview, file=sys.stderr)
                except Exception:
                    print("[Response body not available]", file=sys.stderr)
                print("="*80 + "\n", file=sys.stderr)
            return result
        else:
            # Original httpx implementation
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json",
            }

            # Support both authentication methods
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"

            # Log request details before sending (always log endpoint and payload)
            self._log_request_details("POST", self.api_url, headers, payload, None)

            response = httpx.post(
                self.api_url,
                headers=headers,
                json=payload,
                timeout=420.0
            )
            response.raise_for_status()

            # Log response status if verbose
            if self.verbose:
                print(f"\nResponse Status: {response.status_code}", file=sys.stderr)
                try:
                    response_body = response.text
                    if len(response_body) > 1000:
                        response_body_preview = response_body[:1000] + f"\n... (truncated, total length: {len(response_body)} chars)"
                    else:
                        response_body_preview = response_body
                    print(f"Response Body Preview:", file=sys.stderr)
                    assert response_body_preview is not None
                    print(response_body_preview, file=sys.stderr)
                except Exception:
                    print("[Response body not available]", file=sys.stderr)
                print("="*80 + "\n", file=sys.stderr)

            return response.json()

    def _make_streaming_request(self, payload: Dict[str, Any]):
        """
        Make HTTP POST request to API with streaming response.

        Args:
            payload: Request payload dictionary (should already have extra_params applied)

        Yields:
            Chunks of response text
        """
        if self.backend == "openai":
            # Use OpenAI SDK streaming
            headers = {
                "Content-Type": "application/json",
                "Accept": "text/event-stream, application/json",
            }
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            # Log request details before sending (always log endpoint and payload)
            self._log_request_details("POST", self.api_url, headers, payload, None)
            
            # Ensure stream=True
            payload["stream"] = True
            # Call OpenAI SDK streaming
            assert self.openai_client is not None
            stream = self.openai_client.chat.completions.create(**payload)
            
            # Log response status if verbose
            if self.verbose:
                print(f"\nResponse Status: 200", file=sys.stderr)
                print("Streaming response...", file=sys.stderr)
            
            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                    content = chunk.choices[0].delta.content
                    if content:
                        yield content
        else:
            # Original httpx implementation
            headers = {
                "Content-Type": "application/json",
                "Accept": "text/event-stream, application/json",
            }

            # Support both authentication methods
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"

            # Log request details before sending (always log endpoint and payload)
            self._log_request_details("POST", self.api_url, headers, payload, None)

            with httpx.stream(
                "POST",
                self.api_url,
                headers=headers,
                json=payload,
                timeout=420.0
            ) as response:
                response.raise_for_status()

                # Log response status if verbose
                if self.verbose:
                    print(f"\nResponse Status: {response.status_code}", file=sys.stderr)
                    print("Streaming response...", file=sys.stderr)

                # For OpenAI-compatible streaming responses
                for line in response.iter_lines():
                    if not line:
                        continue

                    # Handle SSE format (data: {...})
                    if line.startswith("data: "):
                        line = line[6:]  # Remove "data: " prefix

                    if line.strip() == "[DONE]":
                        break

                    try:
                        data = json.loads(line)
                        # OpenAI format
                        if "choices" in data and len(data["choices"]) > 0:
                            delta = data["choices"][0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                yield content
                        # Alternative format
                        elif "content" in data:
                            yield data["content"]
                        # Direct text format
                        elif isinstance(data, str):
                            yield data
                    except json.JSONDecodeError:
                        # If not JSON, treat as plain text
                        if line.strip():
                            yield line

    def get_full_response(self, prompt: str, **kwargs) -> str:
        """
        Get full response from API (non-streaming mode).

        Args:
            prompt: Query/prompt string
            **kwargs: Additional parameters that override extra_params if provided

        Returns:
            Formatted response text
        """
        # Determine API type: if q_key is defined, it's a search API (non-OpenAI compatible)
        # Otherwise, it's OpenAI compatible mode (chat API)
        is_search_api = self.q_key is not None

        if is_search_api:
            # Search API - build payload
            assert self.q_key is not None
            question_key = self.q_key
            payload = {
                question_key: prompt[:2000],  # Max 2000 chars
            }

            # Apply extra_params (kwargs take precedence)
            payload = self._apply_extra_params(payload)

            result = self._make_request(payload)

            if 'answer' in result:
                # metaso public API
                # filter out the thinking text which start with '>'

                raw_answer = result.get("answer", "")
                answer = ""
                for line in raw_answer.split('\n'):
                    if line.startswith('>'):
                        continue
                    answer += f"{line}\n"
                return answer

            if result.get("errCode") != 0:
                err_msg = result.get("errMsg", "Unknown error")
                raise RuntimeError(f"API error: {err_msg}")

            data = result.get("data", {})
            text = data.get("text", "")
            references = data.get("references", [])

            # Format response
            response_text = text
            if references:
                response_text += "\n\nReferences:\n"
                for ref in references:
                    title = ref.get("title", "")
                    link = ref.get("link", "")
                    index = ref.get("index", "")
                    response_text += f"  [{index}] {title}\n    {link}\n"

            return response_text
        else:
            # Chat API (OpenAI compatible mode) - build payload
            payload = {}

            # Build messages array
            messages = []

            # Get system_prompt from kwargs first, then from extra_params
            system_prompt = kwargs.get("system_prompt")
            if system_prompt is None:
                system_prompt = self.extra_params.get("system_prompt")

            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            payload["messages"] = messages

            # Add model if available
            if self.model:
                payload["model"] = self.model

            # Get temperature from kwargs first, then from extra_params
            temperature = kwargs.get("temperature")
            if temperature is None and "temperature" in self.extra_params:
                temperature = self.extra_params.get("temperature")
            if temperature is not None:
                payload["temperature"] = temperature

            # Get max_tokens from kwargs first, then from extra_params
            max_tokens = kwargs.get("max_tokens")
            if max_tokens is None:
                max_tokens = self.extra_params.get("max_tokens")
            if max_tokens is not None:
                try:
                    max_tokens = int(max_tokens)
                    payload["max_tokens"] = max_tokens
                except (ValueError, TypeError):
                    pass  # Skip invalid max_tokens

            # Apply extra_params (kwargs and explicit settings above take precedence)
            payload = self._apply_extra_params(payload)

            result = self._make_request(payload)

            # Extract text from response (OpenAI format)
            if "choices" in result and len(result["choices"]) > 0:
                return result["choices"][0]["message"]["content"]
            # Alternative format
            elif "content" in result:
                return result["content"]
            else:
                # Return full response as JSON string if format is unknown
                return json.dumps(result, ensure_ascii=False, indent=2)

    def get_streaming_response(self, prompt: str, **kwargs):
        """
        Get streaming response from API.

        Args:
            prompt: Query/prompt string
            **kwargs: Additional parameters that override extra_params if provided

        Yields:
            Chunks of response text
        """
        # Chat API (OpenAI compatible mode) - build payload
        payload = {}

        # Build messages array
        messages = []

        # Get system_prompt from kwargs first, then from extra_params
        system_prompt = kwargs.get("system_prompt")
        if system_prompt is None:
            system_prompt = self.extra_params.get("system_prompt")

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        payload["messages"] = messages

        # Add model if available
        if self.model:
            payload["model"] = self.model

        # Get temperature from kwargs first, then from extra_params
        temperature = kwargs.get("temperature")
        if temperature is None and "temperature" in self.extra_params:
            temperature = self.extra_params.get("temperature")
        if temperature is not None:
            payload["temperature"] = temperature

        # Get max_tokens from kwargs first, then from extra_params
        max_tokens = kwargs.get("max_tokens")
        if max_tokens is None:
            max_tokens = self.extra_params.get("max_tokens")
        if max_tokens is not None:
            try:
                max_tokens = int(max_tokens)
                payload["max_tokens"] = max_tokens
            except (ValueError, TypeError):
                pass  # Skip invalid max_tokens

        # Ensure stream is enabled
        payload["stream"] = True

        # Apply extra_params (kwargs and explicit settings above take precedence)
        payload = self._apply_extra_params(payload)

        # Override stream to True for streaming
        payload["stream"] = True

        # Stream response
        for chunk in self._make_streaming_request(payload):
            yield chunk

