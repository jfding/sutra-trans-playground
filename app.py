"""Simple Flask web app for LLM API calls."""
import os
import json
import sys
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from pathlib import Path
from llm_client import LLMClient

# Load .env file
project_root = Path(__file__).parent
load_dotenv(dotenv_path=project_root / ".env")

app = Flask(__name__, template_folder='assets', static_folder='assets', static_url_path='/static')
CORS(app)


def get_builtin_template_dir() -> Path:
    return project_root / "prompt-templates"


def get_user_template_dir() -> Path:
    configured_dir = app.config.get("USER_TEMPLATE_DIR")
    if configured_dir:
        return Path(configured_dir)
    return project_root / "user-templates"


def normalize_template_name(raw_name: str) -> str:
    normalized = (raw_name or "").strip()
    if not normalized:
        raise ValueError("Template name is required")
    if "/" in normalized or "\\" in normalized:
        raise ValueError("Template name cannot contain path separators")
    if normalized in {".", ".."}:
        raise ValueError("Template name is invalid")
    if normalized.endswith(".txt"):
        normalized = normalized[:-4]
    normalized = normalized.strip()
    if not normalized:
        raise ValueError("Template name is required")
    return f"{normalized}.txt"


def resolve_template_path(template_name: str) -> Path:
    normalized_name = normalize_template_name(template_name)
    user_path = get_user_template_dir() / normalized_name
    if user_path.exists() and user_path.is_file():
        return user_path
    builtin_path = get_builtin_template_dir() / normalized_name
    if builtin_path.exists() and builtin_path.is_file():
        return builtin_path
    raise FileNotFoundError(f"Template file not found: {normalized_name}")


def list_template_names() -> list[str]:
    template_names: set[str] = set()
    for template_dir in [get_builtin_template_dir(), get_user_template_dir()]:
        if not template_dir.exists():
            continue
        for file in template_dir.glob("*.txt"):
            if file.is_file():
                template_names.add(file.name)
    return sorted(template_names)


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
            "id": "openai-gpt35",
            "name": "OpenAI GPT-3.5 Turbo",
            "api_url": os.getenv("OPENAI_API_URL", "https://api.openai.com/v1/chat/completions"),
            "model": "gpt-3.5-turbo",
            "api_key_name": "OPENAI_API_KEY"
        },
    ]

    if not config_file.exists():
        # If config file doesn't exist, return defaults
        return default_configs

    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            configs = json.load(f)

        if not isinstance(configs, list):
            # If file exists but format is wrong, return defaults
            return default_configs

        return configs
    except (json.JSONDecodeError, IOError) as e:
        # If file exists but can't be read/parsed, return defaults
        print(f"Warning: Failed to load api_configs.json: {e}. Using default configurations.", file=sys.stderr)
        return default_configs


# Load API configurations
DEFAULT_API_CONFIGS = load_api_configs()

# Initialize LLM client cache (will be created per request with selected config)
client_cache = {}


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
    template_path = resolve_template_path(template_name)

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


@app.route('/')
def index():
    """Serve the main page."""
    return render_template('index.html')


@app.route('/api/configs', methods=['GET'])
def list_configs():
    """List all available API endpoint and model configurations."""
    return jsonify({'configs': DEFAULT_API_CONFIGS})


@app.route('/api/templates', methods=['GET'])
def list_templates():
    """List all available templates."""
    return jsonify({'templates': list_template_names()})


@app.route('/api/templates', methods=['POST'])
def create_template():
    """Create or update a user template."""
    data = request.json or {}
    try:
        template_name = normalize_template_name(data.get("name", ""))
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    content = data.get("content", "")
    if not isinstance(content, str) or not content.strip():
        return jsonify({'error': 'Template content is required'}), 400

    template_dir = get_user_template_dir()
    template_dir.mkdir(parents=True, exist_ok=True)
    template_path = template_dir / template_name
    template_path.write_text(content, encoding="utf-8")
    return jsonify({'name': template_name}), 201


@app.route('/api/templates/<template_name>', methods=['GET'])
def get_template(template_name):
    """Get template content."""
    try:
        template_path = resolve_template_path(template_name)
    except (ValueError, FileNotFoundError):
        return jsonify({'error': 'Template not found'}), 404

    try:
        content = template_path.read_text(encoding="utf-8")
        return jsonify({'content': content, 'name': template_name})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/chat', methods=['POST'])
def chat():
    """Handle chat API requests."""
    try:
        data = request.json

        # Get API configuration ID from request
        config_id = data.get('config_id')

        # Find the configuration by ID
        api_config = None
        if config_id:
            for config in DEFAULT_API_CONFIGS:
                if config.get('id') == config_id:
                    api_config = config
                    break

        # If config not found, use first available config or defaults
        if not api_config:
            return jsonify({'error': 'No API configuration available'}), 500

        # Extract configuration values
        api_url = api_config.get('api_url')
        model = api_config.get('model')
        api_key_name = api_config.get('api_key_name')
        default_temperature = api_config.get('default_temperature')
        extra_params = api_config.get('extra_params', {})
        q_key = api_config.get('q_key')
        backend = api_config.get('backend', 'httpx')

        # Detect streaming mode from config
        # Check stream flag: if stream=True or no_stream=False, use streaming
        # If stream=False or no_stream=True, use non-streaming
        # Default to non-streaming if not specified
        use_streaming = False
        if 'stream' in extra_params:
            use_streaming = extra_params.get('stream', False)
        elif 'no_stream' in extra_params:
            use_streaming = not extra_params.get('no_stream', True)

        # Handle temperature: only if config has default_temperature field
        temperature = None
        if default_temperature is not None:
            # Config supports temperature, get from request or use default
            temperature = float(data.get('temperature', default_temperature))
            # Validate temperature
            if not (0.0 <= temperature <= 2.0):
                return jsonify({'error': 'Temperature must be between 0.0 and 2.0'}), 400

        # Validate required fields from config
        if not api_url:
            return jsonify({'error': 'api_url is required in config'}), 500
        if not api_key_name:
            return jsonify({'error': 'api_key_name is required in config'}), 500

        # Handle template-based prompt or direct prompt
        template_name = data.get('template_name')
        input_texts = data.get('input_texts', [])
        prompt = data.get('prompt', '').strip()

        if template_name:
            # Process template with input texts
            try:
                if not input_texts or len(input_texts) == 0:
                    return jsonify({'error': 'At least one input text is required when using a template'}), 400
                prompt = load_template(template_name, input_texts)
            except FileNotFoundError as e:
                return jsonify({'error': str(e)}), 404
            except Exception as e:
                return jsonify({'error': f'Error processing template: {str(e)}'}), 500
        elif not prompt:
            return jsonify({'error': 'Either prompt or template_name with input_texts is required'}), 400

        # Create or get client with specified API URL, model, and api_key_name
        cache_key = f"{api_url}:{model or 'None'}:{backend}"
        if cache_key not in client_cache:
            client_cache[cache_key] = LLMClient(
                api_url=api_url,
                model=model,
                api_key_name=api_key_name,
                verbose=False,
                extra_params=extra_params,
                q_key=q_key,
                backend=backend
            )
        llm_client = client_cache[cache_key]

        try:
            # Pass temperature if available
            kwargs = {}
            if temperature is not None:
                kwargs['temperature'] = temperature

            if use_streaming:
                # Collect streaming response chunks and return as complete response
                response_text = ""
                for chunk in llm_client.get_streaming_response(prompt, **kwargs):
                    response_text += chunk
                return jsonify({'response': response_text})
            else:
                # Return non-streaming response
                response_text = llm_client.get_full_response(prompt, **kwargs)
                return jsonify({'response': response_text})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5858)

