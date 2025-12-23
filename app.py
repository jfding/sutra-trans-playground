"""Simple Flask web app for LLM API calls."""
import os
from flask import Flask, render_template, request, jsonify, Response
from flask_cors import CORS
from dotenv import load_dotenv
from pathlib import Path
from llm_client import LLMClient

# Load .env file
project_root = Path(__file__).parent
load_dotenv(dotenv_path=project_root / ".env")

app = Flask(__name__, template_folder='assets', static_folder='assets', static_url_path='/static')
CORS(app)

# Initialize LLM client
client = None

def get_client():
    """Get or create LLM client instance."""
    global client
    if client is None:
        client = LLMClient(verbose=False)
    return client


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
        raise FileNotFoundError(f"Template file not found: {template_path}")

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


@app.route('/api/templates', methods=['GET'])
def list_templates():
    """List all available templates."""
    template_dir = project_root / "prompt-templates"
    if not template_dir.exists():
        return jsonify({'templates': []})
    
    templates = []
    for file in template_dir.glob("*.txt"):
        templates.append(file.name)
    
    return jsonify({'templates': sorted(templates)})


@app.route('/api/templates/<template_name>', methods=['GET'])
def get_template(template_name):
    """Get template content."""
    template_dir = project_root / "prompt-templates"
    template_path = template_dir / template_name
    
    if not template_path.exists() or not template_path.is_file():
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
        temperature = float(data.get('temperature', 0.7))
        
        # Validate temperature
        if not (0.0 <= temperature <= 2.0):
            return jsonify({'error': 'Temperature must be between 0.0 and 2.0'}), 400
        
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
        
        llm_client = get_client()
        
        # Check API type
        if llm_client.api_type == "openai":
            # OpenAI API
            system_prompt = os.getenv("LLM_SYSTEM_PROMPT")
            max_tokens = None
            if os.getenv("LLM_MAX_TOKENS"):
                try:
                    max_tokens = int(os.getenv("LLM_MAX_TOKENS"))
                except ValueError:
                    pass
            
            # Stream the response
            def generate():
                try:
                    for chunk in llm_client.stream_completion(
                        prompt,
                        system_prompt=system_prompt,
                        temperature=temperature,
                        max_tokens=max_tokens
                    ):
                        yield f"data: {chunk}\n\n"
                    yield "data: [DONE]\n\n"
                except Exception as e:
                    yield f"data: ERROR: {str(e)}\n\n"
            
            return Response(generate(), mimetype='text/event-stream')
        else:
            # Metaso API - doesn't support temperature, but we'll call it anyway
            lang = os.getenv("METASO_LANG")
            session_id = os.getenv("METASO_SESSION_ID")
            if session_id:
                try:
                    session_id = int(session_id)
                except ValueError:
                    session_id = None
            third_party_uid = os.getenv("METASO_THIRD_PARTY_UID")
            enable_mix = os.getenv("METASO_ENABLE_MIX", "false").lower() in ("true", "1", "yes")
            enable_image = os.getenv("METASO_ENABLE_IMAGE", "false").lower() in ("true", "1", "yes")
            engine_type = os.getenv("METASO_ENGINE_TYPE")
            
            def generate():
                try:
                    for message in llm_client.stream_search(
                        prompt,
                        lang=lang,
                        session_id=session_id,
                        third_party_uid=third_party_uid,
                        enable_mix=enable_mix,
                        enable_image=enable_image,
                        engine_type=engine_type
                    ):
                        msg_type = message.get("type")
                        if msg_type == "append-text":
                            text = message.get("text", "")
                            yield f"data: {text}\n\n"
                        elif msg_type == "error":
                            code = message.get("code")
                            msg = message.get("msg", "Unknown error")
                            yield f"data: ERROR: {msg} (code {code})\n\n"
                    yield "data: [DONE]\n\n"
                except Exception as e:
                    yield f"data: ERROR: {str(e)}\n\n"
            
            return Response(generate(), mimetype='text/event-stream')
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5858)

