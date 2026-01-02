"""Main CLI entry point for Metaso search API and OpenAI compatible chat completion."""
import sys
import os
import json
import argparse
from pathlib import Path
from datetime import datetime
from typing import Optional
from dotenv import load_dotenv
from llm_client import LLMClient

# Load .env file from project root
project_root = Path(__file__).parent
load_dotenv(dotenv_path=project_root / ".env")


def load_api_configs():
    """
    Load API/model configurations from JSON file.

    Returns:
        List of API configuration dictionaries
    """
    config_file = project_root / "api_configs.json"

    # Default configurations if file doesn't exist
    default_configs = [
        {
            "id": "metaso-default",
            "name": "Metaso Search",
            "api_url": os.getenv("LLM_API_URL", "https://metaso.cn/api/open/search"),
            "model": None,
            "api_key_name": "METASO_API_KEY"
        },
        {
            "id": "openai-gpt35",
            "name": "OpenAI GPT-3.5 Turbo",
            "api_url": os.getenv("OPENAI_API_URL", "https://api.openai.com/v1/chat/completions"),
            "model": "gpt-3.5-turbo",
            "api_key_name": "OPENAI_API_KEY"
        },
    ]

    if not config_file.exists():
        return default_configs

    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            configs = json.load(f)

        if not isinstance(configs, list):
            return default_configs

        return configs
    except (json.JSONDecodeError, IOError) as e:
        print(f"Warning: Failed to load api_configs.json: {e}. Using default configurations.", file=sys.stderr)
        return default_configs


def save_response(text: str, output_path: Optional[str] = None, api_url: Optional[str] = None) -> str:
    """
    Save response text to file.

    Args:
        text: Text to save
        output_path: Optional output file path. If not provided, generates timestamped filename.
        api_url: API URL for filename prefix (optional)

    Returns:
        Path to saved file
    """
    if output_path:
        filepath = Path(output_path)
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # Determine prefix from API URL if available
        if api_url and "metaso" in api_url.lower():
            prefix = "metaso"
        else:
            prefix = "api"
        filepath = Path(f"{prefix}_response_{timestamp}.txt")

    filepath.write_text(text, encoding="utf-8")
    return str(filepath)


def load_template(template_name: str, input_texts: list[str]) -> str:
    """
    Load a prompt template from ./prompt-templates directory and replace placeholders.

    Args:
        template_name: Name of the template file (e.g., "templ1.txt")
        input_texts: List of texts to replace placeholders:
                     - input_texts[0] -> {input_txt} (required)
                     - input_texts[1] -> {input2_txt} (optional, falls back to input_texts[0] if not provided)
                     - input_texts[2] -> {input3_txt} (optional, falls back to input_texts[0] if not provided)

    Returns:
        Template content with placeholders replaced
    """
    template_dir = project_root / "prompt-templates"
    template_path = template_dir / template_name

    if not template_path.exists():
        print(f"Error: Template file not found: {template_path}", file=sys.stderr)
        sys.exit(1)

    template_content = template_path.read_text(encoding="utf-8")

    # Map placeholders to input texts
    # Use first input as fallback for missing inputs
    input1 = input_texts[0] if len(input_texts) > 0 else ""
    input2 = input_texts[1] if len(input_texts) > 1 else input1
    input3 = input_texts[2] if len(input_texts) > 2 else input1

    # Replace placeholders
    query = template_content.replace("{input_txt}", input1)
    query = query.replace("{input2_txt}", input2)
    query = query.replace("{input3_txt}", input3)

    return query


def main():
    """Main CLI function."""
    parser = argparse.ArgumentParser(
        description="Call Metaso search API or OpenAI chat completion API"
    )
    parser.add_argument(
        "query",
        nargs="*",
        help="Query/prompt (can be multiple, or read from stdin if not provided, or use with --template)"
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
    parser.add_argument(
        "-t", "--template",
        help="Load prompt template from ./prompt-templates directory (e.g., templ1.txt). "
             "Replaces {input_txt}, {input2_txt}, {input3_txt} placeholders with query arguments "
             "(first query -> {input_txt}, second -> {input2_txt}, third -> {input3_txt})."
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Print and save HTTP request details"
    )
    parser.add_argument(
        "-T", "--temperature",
        type=float,
        help="Temperature parameter for API calls (float value)"
    )
    parser.add_argument(
        "-c", "--config",
        help="API configuration ID from api_configs.json (default: first available config)"
    )

    args = parser.parse_args()

    # Handle template loading
    if args.template:
        # Require at least one query argument when using template
        if not args.query or len(args.query) == 0:
            print("Error: At least one query argument is required when using --template.", file=sys.stderr)
            sys.exit(1)
        query = load_template(args.template, args.query)
    else:
        # Get query from argument or stdin (existing behavior)
        if args.query and len(args.query) > 0:
            # Join multiple queries with space if provided
            query = " ".join(args.query)
        else:
            query = sys.stdin.read().strip()
            if not query:
                print("Error: No query provided. Provide as argument or via stdin.", file=sys.stderr)
                sys.exit(1)

    try:
        # Load API configurations
        api_configs = load_api_configs()

        # Find the configuration by ID or use first available
        api_config = None
        if args.config:
            for config in api_configs:
                if config.get('id') == args.config:
                    api_config = config
                    break
            if not api_config:
                print(f"Error: Configuration '{args.config}' not found.", file=sys.stderr)
                sys.exit(1)
        else:
            # Use first available config
            if not api_configs:
                print("Error: No API configuration available.", file=sys.stderr)
                sys.exit(1)
            api_config = api_configs[0]

        # Extract configuration values
        api_url = api_config.get('api_url')
        model = api_config.get('model')
        api_key_name = api_config.get('api_key_name')
        extra_params = api_config.get('extra_params', {})
        q_key = api_config.get('q_key')

        # Initialize client
        client = LLMClient(
            api_url=api_url,
            model=model,
            api_key_name=api_key_name,
            verbose=args.verbose,
            extra_params=extra_params,
            q_key=q_key
        )

        # Determine API type: if q_key is defined, it's a search API (non-OpenAI compatible)
        # Otherwise, it's OpenAI compatible mode (chat API)
        is_search_api = q_key is not None

        if is_search_api:
            print("Calling Search API...", file=sys.stderr)

            # Get search settings from config
            lang = extra_params.get('lang')
            session_id = extra_params.get('session_id')
            if session_id is not None:
                try:
                    session_id = int(session_id)
                except (ValueError, TypeError):
                    session_id = None
            third_party_uid = extra_params.get('third_party_uid')
            enable_mix = extra_params.get('enable_mix', False)
            enable_image = extra_params.get('enable_image', False)
            engine_type = extra_params.get('engine_type')

            # Non-streaming mode
            response_text = client.get_full_response(
                query,
                lang=lang,
                session_id=session_id,
                third_party_uid=third_party_uid,
                enable_mix=enable_mix,
                enable_image=enable_image,
                engine_type=engine_type,
                save_raw_json=args.save_raw_json
            )
            print(response_text)
        else:  # chat API
            print("Calling Chat API...", file=sys.stderr)

            # Get chat settings from config
            default_temperature = api_config.get('default_temperature')
            temperature = default_temperature if default_temperature is not None else 0.7

            if args.temperature:
                try:
                    tt = float(args.temperature)
                    if tt >= 0.0 and tt <= 2.0:
                        temperature = tt
                    else:
                        print(f"Warning: Invalid temperature value, using {temperature}", file=sys.stderr)
                except ValueError:
                    print(f"Warning: Invalid temperature value, using {temperature}", file=sys.stderr)

            max_tokens = extra_params.get('max_tokens')
            if max_tokens is not None:
                try:
                    max_tokens = int(max_tokens)
                except (ValueError, TypeError):
                    max_tokens = None

            system_prompt = extra_params.get('system_prompt')

            # Non-streaming mode
            response_text = client.get_full_response(
                query,
                system_prompt=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens
            )
            print(response_text)

        # Save to file
        output_path = save_response(response_text, args.output, api_url)
        print(f"\nResponse saved to: {output_path}", file=sys.stderr)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
