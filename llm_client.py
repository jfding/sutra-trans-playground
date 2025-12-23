"""API client supporting both Metaso search and OpenAI chat completion."""
import os
import json
import sys
import httpx
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, Iterator, Literal
from dotenv import load_dotenv

# Load .env file from project root
project_root = Path(__file__).parent
load_dotenv(dotenv_path=project_root / ".env")


class LLMClient:
    """Client for calling both Metaso search API and OpenAI chat completion API."""

    def __init__(
        self,
        api_url: Optional[str] = None,
        verbose: bool = False
    ):
        """
        Initialize API client.

        Args:
            api_url: API endpoint URL (defaults to LLM_API_URL env var or auto-detected)
            verbose: If True, print and save HTTP request details
        """
        self.verbose = verbose
        # Get API URL first
        if api_url:
            self.api_url = api_url
        else:
            self.api_url = os.getenv("LLM_API_URL", "")

        # Set default URL if not provided
        if not api_url:
            self.api_url = os.getenv("LLM_API_URL", "https://metaso.cn/api/open/search")

        # Auto-detect API type from URL: if contains 'metaso' (case-insensitive), it's metaso, else openai
        if self.api_url and "metaso" in self.api_url.lower():
            self.api_type = "metaso"
        else:
            self.api_type = "openai"

        # Get API key
        if self.api_type == "metaso":
            # Support both secret-key and api-key authentication
            self.secret_key = os.getenv("METASO_SECRET_KEY")
            self.api_key = os.getenv("LLM_API_KEY") or os.getenv("METASO_API_KEY")
        else:  # openai
            self.api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
            self.secret_key = None

        if self.api_type == "metaso" and not self.api_key and not self.secret_key:
            raise ValueError("API key is required. Set LLM_API_KEY, METASO_API_KEY, or METASO_SECRET_KEY environment variable.")
        elif self.api_type != "metaso" and not self.api_key:
            raise ValueError("API key is required. Set LLM_API_KEY or OPENAI_API_KEY environment variable.")

        # OpenAI-specific settings
        self.model = os.getenv("LLM_MODEL", "gpt-3.5-turbo")

    def _snake_to_camel(self, snake_str: str) -> str:
        """
        Convert SNAKE_CASE to camelCase.

        Args:
            snake_str: String in SNAKE_CASE format

        Returns:
            String in camelCase format
        """
        components = snake_str.lower().split('_')
        return components[0] + ''.join(x.capitalize() for x in components[1:])

    def _get_metaso_env_payload(self) -> Dict[str, Any]:
        """
        Collect all METASO_* environment variables and convert them to payload format.

        Returns:
            Dictionary with payload keys and values from METASO_* env vars
        """
        env_payload = {}

        # Get all environment variables
        for key, value in os.environ.items():
            if key.startswith("METASO_"):
                # Skip authentication keys (they go in headers, not payload)
                if key in ("METASO_SECRET_KEY", "METASO_API_KEY"):
                    continue

                # Remove METASO_ prefix and convert to camelCase
                payload_key = self._snake_to_camel(key[7:])  # Remove "METASO_" prefix

                # Handle special cases for type conversion
                if payload_key in ("enableMix", "enableImage", "stream"):
                    # Boolean fields
                    env_payload[payload_key] = value.lower() in ("true", "1", "yes")
                elif payload_key == "sessionId":
                    # Integer field
                    try:
                        env_payload[payload_key] = int(value)
                    except ValueError:
                        # If conversion fails, skip it
                        continue
                elif value in ('true', 'false', 'True', 'False'):
                    env_payload[payload_key] = value.lower() in ("true", "1", "yes")
                else:
                    # String fields - use as is
                    env_payload[payload_key] = value

        return env_payload

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

        Args:
            method: HTTP method (e.g., "POST")
            url: Request URL
            headers: Request headers (sensitive values will be masked)
            payload: Request payload/body
            response: Optional response object
        """
        if not self.verbose:
            return

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
            # Check if this is a streaming response
            is_streaming = (
                response.headers.get("content-type", "").startswith("text/event-stream") or
                "stream" in str(response.headers.get("accept", "")).lower()
            )

            # Get response body preview
            # For streaming responses, we can't read the body without consuming the stream
            if is_streaming:
                response_body_preview = "[Streaming response - body consumed as event stream]"
            else:
                try:
                    # Try to read response body for non-streaming responses
                    response_body = response.text
                    if len(response_body) > 1000:
                        response_body_preview = response_body[:1000] + f"\n... (truncated, total length: {len(response_body)} chars)"
                    else:
                        response_body_preview = response_body
                except (AttributeError, Exception):
                    # If we can't read the body (e.g., it's already been consumed or it's binary)
                    response_body_preview = "[Response body not available]"

            log_entry["response"] = {
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "body_preview": response_body_preview
            }

        # Print to stderr
        print("\n" + "="*80, file=sys.stderr)
        print("HTTP REQUEST DETAILS", file=sys.stderr)
        print("="*80, file=sys.stderr)
        print(f"Method: {method}", file=sys.stderr)
        print(f"URL: {url}", file=sys.stderr)
        print(f"\nHeaders:", file=sys.stderr)
        for key, value in safe_headers.items():
            print(f"  {key}: {value}", file=sys.stderr)
        print(f"\nPayload:", file=sys.stderr)
        print(json.dumps(payload, indent=2, ensure_ascii=False), file=sys.stderr)

        if response:
            print(f"\nResponse Status: {response.status_code}", file=sys.stderr)
            print(f"Response Headers:", file=sys.stderr)
            for key, value in response.headers.items():
                print(f"  {key}: {value}", file=sys.stderr)
            print(f"\nResponse Body Preview:", file=sys.stderr)
            print(response_body_preview, file=sys.stderr)

        print("="*80 + "\n", file=sys.stderr)

        # Save to file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_filename = f"http_request_{timestamp}.json"
        log_path = project_root / log_filename

        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(log_entry, f, indent=2, ensure_ascii=False)

        print(f"HTTP request details saved to: {log_filename}", file=sys.stderr)

    def search(
        self,
        question: str,
        lang: Optional[str] = None,
        session_id: Optional[int] = None,
        third_party_uid: Optional[str] = None,
        stream: bool = True,
        enable_mix: bool = False,
        enable_image: bool = False,
        engine_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Perform a search using the Metaso API (non-streaming mode).

        Args:
            question: Search question string (required, max 2000 chars)
            lang: Output language type ("zh" for Chinese, "en" for English)
            session_id: Session ID for follow-up questions
            third_party_uid: User ID for tracking/banning
            stream: Whether to use streaming (default: True)
            enable_mix: Enable PDF library mode (default: False)
            enable_image: Enable image mode (default: False)
            engine_type: Search scope ("" for web, "pdf" for library)

        Returns:
            API response as dictionary (non-streaming mode only)
        """
        if self.api_type != "metaso":
            raise ValueError("search() method is only available for Metaso API")

        if stream:
            raise ValueError("search() method is for non-streaming mode. Use stream_search() for streaming.")

        payload = {
            "question": question[:2000],  # Max 2000 chars
        }

        if lang:
            payload["lang"] = lang
        if session_id:
            payload["sessionId"] = session_id
        if third_party_uid:
            payload["thirdPartyUid"] = third_party_uid
        payload["stream"] = False
        if enable_mix:
            payload["enableMix"] = enable_mix
        if enable_image:
            payload["enableImage"] = enable_image
        if engine_type is not None:
            payload["engineType"] = engine_type

        # Add all METASO_* environment variables to payload (only if not already set)
        env_payload = self._get_metaso_env_payload()
        for key, value in env_payload.items():
            if key not in payload:
                payload[key] = value

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        # Support both authentication methods
        if self.secret_key:
            headers["secret-key"] = self.secret_key
        elif self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        response = httpx.post(
            self.api_url,
            headers=headers,
            json=payload,
            timeout=60.0
        )
        response.raise_for_status()

        # Log request details if verbose
        self._log_request_details("POST", self.api_url, headers, payload, response)

        return response.json()

    def stream_search(
        self,
        question: str,
        lang: Optional[str] = None,
        session_id: Optional[int] = None,
        third_party_uid: Optional[str] = None,
        enable_mix: bool = False,
        enable_image: bool = False,
        engine_type: Optional[str] = None
    ) -> Iterator[Dict[str, Any]]:
        """
        Stream search results from the Metaso API.

        Args:
            question: Search question string (required, max 2000 chars)
            lang: Output language type ("zh" for Chinese, "en" for English)
            session_id: Session ID for follow-up questions
            third_party_uid: User ID for tracking/banning
            enable_mix: Enable PDF library mode (default: False)
            enable_image: Enable image mode (default: False)
            engine_type: Search scope ("" for web, "pdf" for library)

        Yields:
            Message dictionaries with types: query, set-reference, append-text, error, heartbeat
        """
        if self.api_type != "metaso":
            raise ValueError("stream_search() method is only available for Metaso API")

        payload = {
            "question": question[:2000],  # Max 2000 chars
            "stream": True,
        }

        if lang:
            payload["lang"] = lang
        if session_id:
            payload["sessionId"] = session_id
        if third_party_uid:
            payload["thirdPartyUid"] = third_party_uid
        if enable_mix:
            payload["enableMix"] = enable_mix
        if enable_image:
            payload["enableImage"] = enable_image
        if engine_type is not None:
            payload["engineType"] = engine_type

        # Add all METASO_* environment variables to payload (only if not already set)
        env_payload = self._get_metaso_env_payload()
        for key, value in env_payload.items():
            if key not in payload:
                payload[key] = value

        headers = {
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            "Connection": "keep-alive",
        }

        # Support both authentication methods
        if self.secret_key:
            headers["secret-key"] = self.secret_key
        elif self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        with httpx.stream("POST", self.api_url, headers=headers, json=payload, timeout=300.0) as response:
            response.raise_for_status()

            # Log request details if verbose (for streaming, log after connection established)
            if self.verbose:
                self._log_request_details("POST", self.api_url, headers, payload, response)

            for line in response.iter_lines():
                if not line.strip():
                    continue

                # Handle [DONE] marker
                if line.strip() == "[DONE]":
                    break

                try:
                    data = json.loads(line)
                    # Skip heartbeat messages
                    if data.get("type") == "heartbeat":
                        continue
                    yield data
                except json.JSONDecodeError:
                    continue

    def stream_completion(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None
    ) -> Iterator[str]:
        """
        Stream completion from OpenAI API.

        Args:
            prompt: User prompt/input
            system_prompt: Optional system prompt
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate

        Yields:
            Text chunks as they arrive
        """
        if self.api_type != "openai":
            raise ValueError("stream_completion() method is only available for OpenAI API")

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "temperature": temperature,
        }

        if max_tokens:
            payload["max_tokens"] = max_tokens

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        with httpx.stream("POST", self.api_url, headers=headers, json=payload, timeout=60.0) as response:
            response.raise_for_status()

            # Log request details if verbose (for streaming, log after connection established)
            if self.verbose:
                self._log_request_details("POST", self.api_url, headers, payload, response)

            for line in response.iter_lines():
                if not line.strip():
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
                    # Alternative format (Anthropic-style)
                    elif "content" in data:
                        yield data["content"]
                except json.JSONDecodeError:
                    continue

    def get_full_response(self, prompt: str, **kwargs) -> str:
        """
        Get full response from API (Metaso search or OpenAI chat).

        Args:
            prompt: Query/prompt string
            **kwargs: Additional arguments (search params for Metaso, chat params for OpenAI)

        Returns:
            Formatted response text
        """
        if self.api_type == "metaso":
            # Extract search-specific kwargs
            lang = kwargs.get("lang")
            session_id = kwargs.get("session_id")
            third_party_uid = kwargs.get("third_party_uid")
            stream = kwargs.get("stream", True)
            enable_mix = kwargs.get("enable_mix", False)
            enable_image = kwargs.get("enable_image", False)
            engine_type = kwargs.get("engine_type")

            save_raw_json = kwargs.get("save_raw_json", False)

            if stream:
                # Streaming mode - collect all text chunks
                full_text = ""
                references = []
                session_id_from_response = None
                result_id = None

                for message in self.stream_search(
                    prompt,
                    lang=lang,
                    session_id=session_id,
                    third_party_uid=third_party_uid,
                    enable_mix=enable_mix,
                    enable_image=enable_image,
                    engine_type=engine_type
                ):
                    msg_type = message.get("type")

                    if msg_type == "query":
                        session_id_from_response = message.get("sessionId")
                        # Keywords in data field (optional)
                        keywords = message.get("data", [])
                        if keywords:
                            full_text += f"Keywords: {', '.join(keywords)}\n\n"

                    elif msg_type == "set-reference":
                        result_id = message.get("resultId")
                        ref_list = message.get("list", [])
                        references = ref_list
                        if ref_list:
                            full_text += "References:\n"
                            for ref in ref_list:
                                title = ref.get("title", "")
                                link = ref.get("link", "")
                                index = ref.get("index", "")
                                full_text += f"  [{index}] {title}\n    {link}\n"
                            full_text += "\n"

                    elif msg_type == "append-text":
                        text = message.get("text", "")
                        full_text += text

                    elif msg_type == "error":
                        code = message.get("code")
                        msg = message.get("msg", "Unknown error")
                        raise RuntimeError(f"Metaso API error (code {code}): {msg}")

                return full_text
            else:
                # Non-streaming mode
                result = self.search(
                    prompt,
                    lang=lang,
                    session_id=session_id,
                    third_party_uid=third_party_uid,
                    stream=False,
                    enable_mix=enable_mix,
                    enable_image=enable_image,
                    engine_type=engine_type
                )

                if result.get("errCode") != 0:
                    err_msg = result.get("errMsg", "Unknown error")
                    raise RuntimeError(f"Metaso API error: {err_msg}")

                if save_raw_json:
                    with open("metaso_response.json", "w") as f:
                        json.dump(result, f, ensure_ascii=False, indent=2)
                    return "Raw JSON saved to metaso_response.json"

                data = result.get("data", {})
                text = data.get("text", "")
                references = data.get("references", [])

                # Format response
                response_text = text
                if references:
                    response_text += "References:\n"
                    for ref in references:
                        title = ref.get("title", "")
                        link = ref.get("link", "")
                        index = ref.get("index", "")
                        response_text += f"  [{index}] {title}\n    {link}\n"
                    response_text += "\n"

                return response_text
        else:  # openai
            # Extract chat-specific kwargs
            chat_kwargs = {
                "system_prompt": kwargs.get("system_prompt"),
                "temperature": kwargs.get("temperature", 0.7),
                "max_tokens": kwargs.get("max_tokens")
            }
            return "".join(self.stream_completion(prompt, **chat_kwargs))

