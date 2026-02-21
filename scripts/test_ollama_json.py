#!/usr/bin/env python3
"""
Test script for Ollama JSON compliance.

Tests two approaches:
1. Instructor library with OpenAI SDK (GBNF grammar enforcement)
2. Direct Ollama API with field name mapping (fallback)

Usage:
    python test_ollama_json.py

Requirements:
    pip install instructor openai ollama pydantic

Environment:
    OLLAMA_BASE_URL=http://75.154.254.174:11434 (default)
    OLLAMA_MODEL=mistral:7b-instruct (default)
"""

import os
import sys
import time
import json
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# Pydantic model for position sizing
class PositionSizeDecision(BaseModel):
    """Structured position sizing decision output."""
    
    lot_quantity: float = Field(..., gt=0.0, description="Position size in lots")
    dynamic_risk_percentage: float = Field(..., ge=0.0, le=10.0, description="Risk as % of capital")
    kelly_fraction_applied: float = Field(..., ge=0.0, le=1.0, description="Kelly fraction used")
    base_size: float = Field(..., description="Base position size")
    adjustments: Dict[str, float] = Field(default_factory=dict, description="Adjustment factors")
    reasoning: str = Field(..., description="Explanation")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence level")
    risk_metrics: Dict[str, Any] = Field(default_factory=dict, description="Risk metrics")


# Field name mapping for common mistakes
FIELD_MAPPING = {
    # lot_quantity variations
    "position_size": "lot_quantity",
    "positionSize": "lot_quantity",
    "position": "lot_quantity",
    "size": "lot_quantity",
    "lots": "lot_quantity",
    "lot_size": "lot_quantity",
    "lotSize": "lot_quantity",
    
    # dynamic_risk_percentage variations
    "risk_percent": "dynamic_risk_percentage",
    "risk_percentage": "dynamic_risk_percentage",
    "riskPercentage": "dynamic_risk_percentage",
    "risk_pct": "dynamic_risk_percentage",
    "riskPct": "dynamic_risk_percentage",
    "risk": "dynamic_risk_percentage",
    
    # kelly_fraction_applied variations
    "kelly_fraction": "kelly_fraction_applied",
    "kellyFraction": "kelly_fraction_applied",
    "kelly": "kelly_fraction_applied",
    
    # confidence variations
    "confidence_level": "confidence",
    "confidenceLevel": "confidence",
}


def map_field_names(data: dict) -> dict:
    """Map common incorrect field names to correct ones."""
    result = {}
    for key, value in data.items():
        mapped_key = FIELD_MAPPING.get(key, key)
        result[mapped_key] = value
    return result


def test_instructor_approach():
    """Test 1: Instructor library with OpenAI SDK."""
    print("\n" + "="*60)
    print("TEST 1: Instructor Library (OpenAI SDK -> Ollama)")
    print("="*60)
    
    try:
        import instructor
        from openai import OpenAI
    except ImportError as e:
        print(f"❌ Missing dependency: {e}")
        print("   Run: pip install instructor openai")
        return False
    
    base_url = os.getenv("OLLAMA_BASE_URL", "http://75.154.254.174:11434")
    model = os.getenv("OLLAMA_MODEL", "mistral:7b-instruct")
    
    print(f"📍 Ollama URL: {base_url}")
    print(f"🤖 Model: {model}")
    
    # Create OpenAI client pointed at Ollama
    openai_client = OpenAI(
        base_url=f"{base_url}/v1",
        api_key="ollama",
        timeout=60.0,
    )
    
    # Wrap with instructor
    client = instructor.from_openai(openai_client, mode=instructor.Mode.JSON)
    
    system_prompt = """You MUST return ONLY valid JSON with these EXACT field names:
- lot_quantity (number)
- dynamic_risk_percentage (number)
- kelly_fraction_applied (number 0-1)
- base_size (number)
- adjustments (object)
- reasoning (string)
- confidence (number 0-1)
- risk_metrics (object)

Do NOT change field names. Output valid JSON only."""

    user_prompt = """Calculate position size:
- Symbol: Gold
- Kelly fraction: 0.25
- Account balance: $50,000
- Current drawdown: 5%
- Trade conviction: 0.8

Output the position sizing decision as JSON."""

    print("\n⏳ Calling Ollama via instructor...")
    start_time = time.time()
    
    try:
        result = client.chat.completions.create(
            model=model,
            response_model=PositionSizeDecision,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_retries=3,
            temperature=0.0,
        )
        
        elapsed = time.time() - start_time
        
        print(f"✅ SUCCESS in {elapsed:.1f}s")
        print(f"\n📊 Result:")
        print(f"   lot_quantity: {result.lot_quantity}")
        print(f"   dynamic_risk_percentage: {result.dynamic_risk_percentage}%")
        print(f"   kelly_fraction_applied: {result.kelly_fraction_applied}")
        print(f"   confidence: {result.confidence}")
        print(f"   reasoning: {result.reasoning[:80]}...")
        
        return True
        
    except Exception as e:
        elapsed = time.time() - start_time
        print(f"❌ FAILED in {elapsed:.1f}s: {e}")
        return False


def test_direct_ollama_with_mapping():
    """Test 2: Direct Ollama API with field name mapping."""
    print("\n" + "="*60)
    print("TEST 2: Direct Ollama API + Field Mapping")
    print("="*60)
    
    try:
        from ollama import chat
    except ImportError as e:
        print(f"❌ Missing dependency: {e}")
        print("   Run: pip install ollama")
        return False
    
    base_url = os.getenv("OLLAMA_BASE_URL", "http://75.154.254.174:11434")
    model = os.getenv("OLLAMA_MODEL", "mistral:7b-instruct")
    
    # Set OLLAMA_HOST for the ollama library
    os.environ["OLLAMA_HOST"] = base_url
    
    print(f"📍 Ollama URL: {base_url}")
    print(f"🤖 Model: {model}")
    
    system_prompt = """You are a position sizing expert. Return ONLY valid JSON.

Required fields:
- lot_quantity (number)
- dynamic_risk_percentage (number)
- kelly_fraction_applied (number)
- base_size (number)
- adjustments (object)
- reasoning (string)
- confidence (number)
- risk_metrics (object)

Output valid JSON only. No markdown. No explanations."""

    user_prompt = """Calculate position size for Gold trade:
- Kelly: 0.25
- Account: $50,000
- Drawdown: 5%
- Conviction: 0.8"""

    print("\n⏳ Calling Ollama directly...")
    start_time = time.time()
    
    try:
        response = chat(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            format="json",
            options={
                "temperature": 0.0,
                "num_predict": 1000,
            },
        )
        
        elapsed = time.time() - start_time
        
        # Extract content
        content = response["message"]["content"] if isinstance(response, dict) else response.message.content
        
        print(f"⏱️  Response time: {elapsed:.1f}s")
        print(f"\n📝 Raw response:\n{content[:500]}")
        
        # Clean up Python dict syntax
        if "'" in content:
            content = content.replace("'", '"')
            content = content.replace("True", "true")
            content = content.replace("False", "false")
            content = content.replace("None", "null")
        
        # Parse JSON
        data = json.loads(content)
        print(f"\n🔑 Original field names: {list(data.keys())}")
        
        # Map field names
        mapped_data = map_field_names(data)
        print(f"🔄 Mapped field names: {list(mapped_data.keys())}")
        
        # Validate against Pydantic
        try:
            result = PositionSizeDecision(**mapped_data)
            print(f"\n✅ VALIDATION PASSED")
            print(f"   lot_quantity: {result.lot_quantity}")
            print(f"   dynamic_risk_percentage: {result.dynamic_risk_percentage}%")
            return True
        except Exception as ve:
            print(f"\n⚠️  VALIDATION FAILED: {ve}")
            print(f"   Missing fields: {set(PositionSizeDecision.model_fields.keys()) - set(mapped_data.keys())}")
            return False
        
    except Exception as e:
        elapsed = time.time() - start_time
        print(f"❌ FAILED in {elapsed:.1f}s: {e}")
        return False


def test_connectivity():
    """Test 0: Basic Ollama connectivity."""
    print("\n" + "="*60)
    print("TEST 0: Ollama Connectivity")
    print("="*60)
    
    base_url = os.getenv("OLLAMA_BASE_URL", "http://75.154.254.174:11434")
    model = os.getenv("OLLAMA_MODEL", "mistral:7b-instruct")
    
    print(f"📍 Ollama URL: {base_url}")
    print(f"🤖 Target model: {model}")
    
    try:
        import requests
        
        # Test /api/tags endpoint
        response = requests.get(f"{base_url}/api/tags", timeout=5)
        if response.status_code == 200:
            models = response.json().get("models", [])
            model_names = [m.get("name", "") for m in models]
            print(f"✅ Connected! Found {len(models)} models")
            print(f"   Available: {', '.join(model_names[:5])}...")
            
            if any(model in m for m in model_names):
                print(f"✅ Target model '{model}' is available")
                return True
            else:
                print(f"⚠️  Target model '{model}' not found!")
                print(f"   Run: ollama pull {model}")
                return False
        else:
            print(f"❌ HTTP {response.status_code}: {response.text}")
            return False
            
    except requests.exceptions.ConnectionError:
        print(f"❌ Cannot connect to Ollama at {base_url}")
        print(f"   Make sure Ollama is running: ollama serve")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("OLLAMA JSON COMPLIANCE TEST SUITE")
    print("="*60)
    
    # Load .env if present
    try:
        from dotenv import load_dotenv
        load_dotenv()
        print("✅ Loaded .env file")
    except ImportError:
        print("ℹ️  python-dotenv not installed, using environment variables")
    
    results = {}
    
    # Test 0: Connectivity
    results["connectivity"] = test_connectivity()
    
    if not results["connectivity"]:
        print("\n❌ Cannot proceed without Ollama connection")
        return
    
    # Test 1: Instructor approach
    results["instructor"] = test_instructor_approach()
    
    # Test 2: Direct Ollama + mapping
    results["direct_mapping"] = test_direct_ollama_with_mapping()
    
    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    for test, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"   {test}: {status}")
    
    # Recommendation
    print("\n📋 RECOMMENDATION:")
    if results.get("instructor"):
        print("   Use Instructor library (guaranteed schema compliance)")
    elif results.get("direct_mapping"):
        print("   Use Direct Ollama + Field Mapping (fast fallback)")
    else:
        print("   Consider GPT-4o (FREE tier) as fallback")


if __name__ == "__main__":
    main()
