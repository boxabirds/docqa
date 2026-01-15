"""
Test local VLM figure captioning with OpenAI-compatible endpoints (Ollama, vLLM, etc.)

Configuration (environment variables):
    KH_VLM_ENDPOINT  - VLM API endpoint (default: http://ollama:11434/v1/chat/completions)
    KH_VLM_MODEL     - Vision model name (default: qwen2.5vl:7b)
    TEST_VLM_HOST    - Override hostname for testing (default: from endpoint)
    TEST_TIMEOUT     - Request timeout in seconds (default: 60)

Usage:
    # From inside kotaemon container:
    KH_VLM_MODEL=qwen2.5vl:7b KH_VLM_ENDPOINT=http://ollama:11434/v1/chat/completions python test_local_vlm.py

    # From host machine testing container:
    KH_VLM_MODEL=qwen2.5vl:7b KH_VLM_ENDPOINT=http://localhost:11434/v1/chat/completions python test_local_vlm.py
"""
import base64
import os
import sys
import struct
import zlib

# Test configuration with defaults
CONFIG = {
    "vlm_endpoint": os.environ.get("KH_VLM_ENDPOINT", "http://ollama:11434/v1/chat/completions"),
    "vlm_model": os.environ.get("KH_VLM_MODEL", "qwen2.5vl:7b"),
    "timeout": int(os.environ.get("TEST_TIMEOUT", "60")),
}

# Ensure Azure mode is disabled for local testing
os.environ.pop("AZURE_OPENAI_API_KEY", None)
os.environ["KH_VLM_MODEL"] = CONFIG["vlm_model"]

# Import after setting env vars
from kotaemon.loaders.utils.gpt4v import generate_gpt4v, _get_vlm_config


def create_test_png(width: int, height: int, rgb: tuple) -> bytes:
    """Create a minimal valid PNG image."""
    def chunk(chunk_type, data):
        return (struct.pack('>I', len(data)) + chunk_type + data +
                struct.pack('>I', zlib.crc32(chunk_type + data) & 0xffffffff))

    raw_data = b''
    for _ in range(height):
        raw_data += b'\x00'  # filter byte
        for _ in range(width):
            raw_data += bytes(rgb)

    return (b'\x89PNG\r\n\x1a\n' +
            chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)) +
            chunk(b'IDAT', zlib.compress(raw_data)) +
            chunk(b'IEND', b''))


def test_vlm_config_local_mode():
    """Test that config correctly detects local mode when KH_VLM_MODEL is set."""
    print(f"  Model: {CONFIG['vlm_model']}")

    config = _get_vlm_config()

    assert config["model"] == CONFIG["vlm_model"], \
        f"Expected model {CONFIG['vlm_model']}, got {config['model']}"
    assert "Authorization" in config["headers"], \
        "Expected Authorization header for local mode"
    assert "api-key" not in config["headers"], \
        "Should not have Azure api-key header in local mode"

    print("  ✓ Config correctly detects local mode")
    return True


def test_vlm_endpoint_reachable():
    """Test that the VLM endpoint is reachable."""
    import requests

    print(f"  Endpoint: {CONFIG['vlm_endpoint']}")

    # Extract base URL for health check
    base_url = CONFIG['vlm_endpoint'].rsplit('/v1/', 1)[0]

    try:
        resp = requests.get(f"{base_url}/api/tags", timeout=5)
        models = resp.json().get("models", [])
        model_names = [m.get("name", "") for m in models]
        print(f"  Available models: {', '.join(model_names)}")

        if CONFIG["vlm_model"] not in model_names and f"{CONFIG['vlm_model']}:latest" not in model_names:
            # Check partial match
            matching = [m for m in model_names if CONFIG["vlm_model"].split(":")[0] in m]
            if not matching:
                print(f"  ⚠ Warning: Model {CONFIG['vlm_model']} not found in available models")

        print("  ✓ Endpoint reachable")
        return True
    except Exception as e:
        print(f"  ✗ Failed to reach endpoint: {e}")
        return False


def test_generate_caption():
    """Test actual figure captioning with the configured VLM."""
    print(f"  Endpoint: {CONFIG['vlm_endpoint']}")
    print(f"  Model: {CONFIG['vlm_model']}")
    print(f"  Timeout: {CONFIG['timeout']}s")

    # Create a 50x50 solid blue test image
    png_data = create_test_png(50, 50, (30, 100, 200))
    image_b64 = base64.b64encode(png_data).decode()
    image_url = f"data:image/png;base64,{image_b64}"

    print("  Sending request...")

    result = generate_gpt4v(
        endpoint=CONFIG["vlm_endpoint"],
        images=image_url,
        prompt="What color is this solid colored image? Reply with just the color name.",
        max_tokens=50,
    )

    if not result:
        print("  ✗ Empty response from VLM")
        return False

    print(f"  Response: {result}")
    print("  ✓ Caption generated successfully")
    return True


def test_docling_integration():
    """Test that the patched module integrates correctly with Docling reader."""
    try:
        from kotaemon.loaders import DoclingReader

        reader = DoclingReader()
        reader.vlm_endpoint = CONFIG["vlm_endpoint"]

        print(f"  DoclingReader.vlm_endpoint: {reader.vlm_endpoint}")
        print("  ✓ DoclingReader accepts VLM endpoint")
        return True
    except Exception as e:
        print(f"  ✗ DoclingReader integration failed: {e}")
        return False


def main():
    print("=" * 60)
    print("Local VLM Figure Captioning Test")
    print("=" * 60)
    print(f"\nConfiguration:")
    for key, value in CONFIG.items():
        print(f"  {key}: {value}")
    print()

    tests = [
        ("Config Detection", test_vlm_config_local_mode),
        ("Endpoint Reachable", test_vlm_endpoint_reachable),
        ("Caption Generation", test_generate_caption),
        ("Docling Integration", test_docling_integration),
    ]

    results = []
    for name, test_fn in tests:
        print(f"\n[{name}]")
        try:
            passed = test_fn()
            results.append((name, passed))
        except Exception as e:
            print(f"  ✗ Exception: {e}")
            results.append((name, False))

    print("\n" + "=" * 60)
    print("Results:")
    all_passed = True
    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {status}: {name}")
        if not passed:
            all_passed = False

    print("=" * 60)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
