"""API client supporting both search APIs and OpenAI-compatible chat completion APIs."""
import os
import json
import sys
import httpx
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any
from dotenv import load_dotenv

# Load .env file from project root
project_root = Path(__file__).parent
load_dotenv(dotenv_path=project_root / ".env")


class LLMClient:
    """Client for calling LLM APIs, supporting both search APIs and OpenAI-compatible chat APIs."""

    def __init__(
        self,
        api_url: str,
        model: str,
        api_key_name: str = None,
        verbose: bool = False,
        extra_params: Optional[Dict[str, Any]] = None,
        q_key: Optional[str] = None
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
            raise ValueError(f"API key is required. Set {api_key_name} environment variable.")

        self.model = model

        # Store extra parameters that will be automatically added to payload
        self.extra_params = extra_params or {}

        # Store question key name (if None, means OpenAI compatible mode)
        self.q_key = q_key

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
            try:
                # Try to read response body
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
            timeout=60.0
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
                print(response_body_preview, file=sys.stderr)
            except Exception:
                print("[Response body not available]", file=sys.stderr)
            print("="*80 + "\n", file=sys.stderr)

        return response.json()

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
            question_key = self.q_key
            payload = {
                question_key: prompt[:2000],  # Max 2000 chars
            }

            # Apply extra_params (kwargs take precedence)
            payload = self._apply_extra_params(payload)

            result = self._make_request(payload)

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

