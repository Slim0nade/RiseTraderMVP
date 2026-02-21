#!/usr/bin/env python3
"""
Quick Ollama Connection Test Script

Tests Ollama connectivity and generates a simple JSON response.
"""
import requests
import json
import sys
from datetime import datetime

def test_ollama_connection(base_url: str = "http://192.168.0.123:11434"):
    """Test Ollama connection with a simple generation."""

    print(f"Testing Ollama connection at {base_url}")
    print("=" * 60)

    # Test 1: Check if Ollama is accessible
    print("\n1. Checking Ollama API accessibility...")
    try:
        response = requests.get(f"{base_url}/api/tags", timeout=5)
        response.raise_for_status()
        models = response.json().get("models", [])
        print(f"✅ Ollama is accessible! Found {len(models)} models:")
        for model in models:
            size_gb = model.get("size", 0) / (1024**3)
            print(f"   - {model.get('name')}: {size_gb:.2f} GB")
    except Exception as e:
        print(f"❌ Failed to connect to Ollama: {e}")
        return False

    # Test 2: Generate a simple JSON response
    print("\n2. Testing JSON generation with llama3.1:8b...")
    try:
        payload = {
            "model": "llama3.1:8b",
            "prompt": "Generate a JSON object with trading signal. Format: {\"signal\": \"buy\" or \"sell\", \"confidence\": 0.0-1.0, \"reason\": \"brief reason\"}. Only return the JSON, nothing else.",
            "stream": False,
            "format": "json"
        }

        start_time = datetime.now()
        response = requests.post(
            f"{base_url}/api/generate",
            json=payload,
            timeout=30
        )
        response.raise_for_status()
        elapsed = (datetime.now() - start_time).total_seconds()

        result = response.json()
        generated_text = result.get("response", "")

        print(f"✅ Generation successful! (took {elapsed:.2f}s)")
        print(f"\nGenerated JSON:")
        print(generated_text)

        # Try to parse it as JSON
        try:
            parsed = json.loads(generated_text)
            print(f"\n✅ Valid JSON! Parsed structure:")
            print(json.dumps(parsed, indent=2))
        except json.JSONDecodeError as e:
            print(f"\n⚠️  Generated text is not valid JSON: {e}")

    except Exception as e:
        print(f"❌ Failed to generate response: {e}")
        return False

    # Test 3: Test with instructor-style schema
    print("\n3. Testing structured output (trading decision)...")
    try:
        schema_prompt = """Generate a trading decision in JSON format with this exact structure:
{
  "action": "BUY" or "SELL" or "HOLD",
  "quantity": a number between 0.01 and 1.0,
  "stop_loss": a price number,
  "take_profit": a price number,
  "confidence": a number between 0 and 1,
  "reasoning": "brief explanation"
}
Only return the JSON object, nothing else."""

        payload = {
            "model": "llama3.1:8b",
            "prompt": schema_prompt,
            "stream": False,
            "format": "json"
        }

        start_time = datetime.now()
        response = requests.post(
            f"{base_url}/api/generate",
            json=payload,
            timeout=30
        )
        response.raise_for_status()
        elapsed = (datetime.now() - start_time).total_seconds()

        result = response.json()
        generated_text = result.get("response", "")

        print(f"✅ Generation successful! (took {elapsed:.2f}s)")
        print(f"\nGenerated trading decision:")
        print(generated_text)

        # Validate structure
        try:
            decision = json.loads(generated_text)
            required_fields = ["action", "quantity", "stop_loss", "take_profit", "confidence", "reasoning"]
            missing = [f for f in required_fields if f not in decision]

            if not missing:
                print(f"\n✅ All required fields present!")
                print(f"   Action: {decision['action']}")
                print(f"   Quantity: {decision['quantity']}")
                print(f"   Confidence: {decision['confidence']}")
            else:
                print(f"\n⚠️  Missing fields: {missing}")

        except json.JSONDecodeError as e:
            print(f"\n⚠️  Generated text is not valid JSON: {e}")

    except Exception as e:
        print(f"❌ Failed to generate structured decision: {e}")
        return False

    print("\n" + "=" * 60)
    print("✅ All Ollama tests passed!")
    return True


if __name__ == "__main__":
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://192.168.0.123:11434"
    success = test_ollama_connection(base_url)
    sys.exit(0 if success else 1)
