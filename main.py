"""Main CLI entry point for Metaso search API and OpenAI compatible chat completion."""
import sys
import os
import argparse
from pathlib import Path
from datetime import datetime
from typing import Optional
from dotenv import load_dotenv
from llm_client import LLMClient

# Load .env file from project root
project_root = Path(__file__).parent
load_dotenv(dotenv_path=project_root / ".env")


def save_response(text: str, output_path: Optional[str] = None, api_type: str = "metaso") -> str:
    """
    Save response text to file.
    
    Args:
        text: Text to save
        output_path: Optional output file path. If not provided, generates timestamped filename.
        api_type: API type for filename prefix
        
    Returns:
        Path to saved file
    """
    if output_path:
        filepath = Path(output_path)
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        prefix = "metaso" if api_type == "metaso" else "openai"
        filepath = Path(f"{prefix}_response_{timestamp}.txt")
    
    filepath.write_text(text, encoding="utf-8")
    return str(filepath)


def main():
    """Main CLI function."""
    parser = argparse.ArgumentParser(
        description="Call Metaso search API or OpenAI chat completion API"
    )
    parser.add_argument(
        "query",
        nargs="?",
        help="Query/prompt (or read from stdin if not provided)"
    )
    parser.add_argument(
        "-o", "--output",
        help="Output file path (default: auto-generated timestamped filename)"
    )
    parser.add_argument(
        "-j", "--save-raw-json",
        action="store_true",
        help="Save raw JSON response to file"
    )
    
    args = parser.parse_args()
    
    # Get query from argument or stdin
    if args.query:
        query = args.query
    else:
        query = sys.stdin.read().strip()
        if not query:
            print("Error: No query provided. Provide as argument or via stdin.", file=sys.stderr)
            sys.exit(1)
    
    try:
        # Initialize client (API type auto-detected from URL)
        client = LLMClient()
        
        # Get response based on API type
        if client.api_type == "metaso":
            print("Calling Metaso API...", file=sys.stderr)
            
            # Get Metaso settings from environment variables
            lang = os.getenv("METASO_LANG")  # "zh" or "en", optional
            session_id = os.getenv("METASO_SESSION_ID")
            if session_id:
                try:
                    session_id = int(session_id)
                except ValueError:
                    session_id = None
            third_party_uid = os.getenv("METASO_THIRD_PARTY_UID")
            stream = os.getenv("METASO_STREAM", "true").lower() in ("true", "1", "yes")
            enable_mix = os.getenv("METASO_ENABLE_MIX", "false").lower() in ("true", "1", "yes")
            enable_image = os.getenv("METASO_ENABLE_IMAGE", "false").lower() in ("true", "1", "yes")
            engine_type = os.getenv("METASO_ENGINE_TYPE")  # "" for web, "pdf" for library
            
            if stream:
                # Streaming mode
                response_text = ""
                for message in client.stream_search(
                    query,
                    lang=lang,
                    session_id=session_id,
                    third_party_uid=third_party_uid,
                    enable_mix=enable_mix,
                    enable_image=enable_image,
                    engine_type=engine_type
                ):
                    msg_type = message.get("type")
                    
                    if msg_type == "query":
                        keywords = message.get("data", [])
                        if keywords:
                            print(f"Keywords: {', '.join(keywords)}", file=sys.stderr)
                    
                    elif msg_type == "set-reference":
                        ref_list = message.get("list", [])
                        if ref_list:
                            print("\nReferences:", file=sys.stderr)
                            for ref in ref_list:
                                title = ref.get("title", "")
                                link = ref.get("link", "")
                                index = ref.get("index", "")
                                print(f"  [{index}] {title}", file=sys.stderr)
                                print(f"    {link}", file=sys.stderr)
                            print("", file=sys.stderr)
                    
                    elif msg_type == "append-text":
                        text = message.get("text", "")
                        print(text, end="", flush=True)
                        response_text += text
                    
                    elif msg_type == "error":
                        code = message.get("code")
                        msg = message.get("msg", "Unknown error")
                        print(f"\nError (code {code}): {msg}", file=sys.stderr)
                        sys.exit(1)
                
                print()  # Newline after streaming
            else:
                # Non-streaming mode
                response_text = client.get_full_response(
                    query,
                    lang=lang,
                    session_id=session_id,
                    third_party_uid=third_party_uid,
                    stream=False,
                    enable_mix=enable_mix,
                    enable_image=enable_image,
                    engine_type=engine_type,
                    save_raw_json=args.save_raw_json
                )
                print(response_text)
        else:  # openai
            print("Calling OpenAI API...", file=sys.stderr)
            
            # Get OpenAI settings from environment variables
            temperature = 0.7  # Default value
            if os.getenv("LLM_TEMPERATURE"):
                try:
                    temperature = float(os.getenv("LLM_TEMPERATURE"))
                except ValueError:
                    print("Warning: Invalid LLM_TEMPERATURE value, using default 0.7", file=sys.stderr)
                    temperature = 0.7
            
            max_tokens = None
            if os.getenv("LLM_MAX_TOKENS"):
                try:
                    max_tokens = int(os.getenv("LLM_MAX_TOKENS"))
                except ValueError:
                    print("Warning: Invalid LLM_MAX_TOKENS value, ignoring", file=sys.stderr)
            
            system_prompt = os.getenv("LLM_SYSTEM_PROMPT")
            no_stream = os.getenv("LLM_NO_STREAM", "false").lower() in ("true", "1", "yes")
            
            if no_stream:
                # Non-streaming mode
                response_text = client.get_full_response(
                    query,
                    system_prompt=system_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens
                )
                print(response_text)
            else:
                # Streaming mode
                response_text = ""
                for chunk in client.stream_completion(
                    query,
                    system_prompt=system_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens
                ):
                    print(chunk, end="", flush=True)
                    response_text += chunk
                print()  # Newline after streaming
        
        # Save to file
        output_path = save_response(response_text, args.output, client.api_type)
        print(f"\nResponse saved to: {output_path}", file=sys.stderr)
        
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
