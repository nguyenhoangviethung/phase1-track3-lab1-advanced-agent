"""Real LLM Runtime using OpenAI API or Ollama"""
from __future__ import annotations
import json
import os
import time
from typing import Optional
from .schemas import QAExample, JudgeResult, ReflectionEntry
from .utils import normalize_answer
from .prompts import ACTOR_SYSTEM, EVALUATOR_SYSTEM, REFLECTOR_SYSTEM

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

try:
    import tiktoken
    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False

import requests


class LLMRuntime:
    """LLM Runtime supporting OpenAI API or Ollama"""
    
    def __init__(
        self,
        model: str = "gpt-4-turbo",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        ollama_endpoint: str = "http://localhost:11434",
        use_ollama: bool = False,
        temperature: float = 0.7,
        max_tokens: int = 500,
    ):
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.ollama_endpoint = ollama_endpoint
        self.use_ollama = use_ollama
        
        if not use_ollama and OPENAI_AVAILABLE:
            api_key = api_key or os.getenv("OPENAI_API_KEY")
            base_url = base_url or os.getenv("OPENAI_BASE_URL")
            self.client = OpenAI(api_key=api_key, base_url=base_url)
        else:
            self.client = None
        
        # Initialize tokenizer for accurate token counting
        self.tokenizer = None
        if TIKTOKEN_AVAILABLE:
            try:
                self.tokenizer = tiktoken.encoding_for_model("gpt-4")
            except:
                pass
    
    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count for text"""
        if self.tokenizer:
            return len(self.tokenizer.encode(text))
        # Fallback: rough approximation (1 token ≈ 4 chars)
        return max(1, len(text) // 4)
    
    def _call_openai(self, system: str, user_message: str) -> tuple[str, int, float]:
        """Call OpenAI API and return response, token count, and latency"""
        start_time = time.time()
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_message},
            ],
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        
        latency_ms = (time.time() - start_time) * 1000
        content = response.choices[0].message.content
        tokens = response.usage.total_tokens if response.usage else 0
        
        return content, tokens, latency_ms
    
    def _call_ollama(self, system: str, user_message: str) -> tuple[str, int, float]:
        """Call local Ollama instance"""
        start_time = time.time()
        
        url = f"{self.ollama_endpoint}/api/chat"
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user_message},
        ]
        
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "temperature": self.temperature,
        }
        
        try:
            response = requests.post(url, json=payload, timeout=60)
            response.raise_for_status()
            data = response.json()
            
            latency_ms = (time.time() - start_time) * 1000
            content = data.get("message", {}).get("content", "")
            
            # Accurate token counting for response and input
            input_tokens = self._estimate_tokens(system + user_message)
            output_tokens = self._estimate_tokens(content)
            total_tokens = input_tokens + output_tokens
            
            return content, total_tokens, latency_ms
        except Exception as e:
            raise RuntimeError(f"Failed to call Ollama: {e}. Make sure Ollama is running on {self.ollama_endpoint}")
    
    def call_llm(self, system: str, user_message: str) -> tuple[str, int, float]:
        """Call LLM and return response, token count, and latency"""
        if self.use_ollama or not self.client:
            return self._call_ollama(system, user_message)
        return self._call_openai(system, user_message)
    
    def actor_answer(
        self,
        example: QAExample,
        attempt_id: int,
        reflection_memory: list[str],
    ) -> tuple[str, int, float]:
        """Generate answer using Actor agent"""
        context_text = "\n\n".join(f"{chunk.title}:\n{chunk.text}" for chunk in example.context)
        
        user_message = f"""Question: {example.question}

Context:
{context_text}

{"Previous reflection guidance:" + chr(10) + chr(10).join(f"- {mem}" for mem in reflection_memory) if reflection_memory else ""}

Please provide your final answer to the question based on the context."""
        
        response, tokens, latency = self.call_llm(ACTOR_SYSTEM, user_message)
        
        # Extract answer from response (look for common patterns)
        answer = response.strip()
        if "Answer:" in answer:
            answer = answer.split("Answer:")[-1].strip()
        
        return answer, tokens, latency
    
    def evaluator(self, example: QAExample, answer: str) -> tuple[JudgeResult, int, float]:
        """Evaluate answer using Evaluator agent"""
        user_message = f"""Question: {example.question}
Gold Answer: {example.gold_answer}
Predicted Answer: {answer}

Evaluate if the predicted answer is correct. Compare them after normalization and return JSON."""
        
        response, tokens, latency = self.call_llm(EVALUATOR_SYSTEM, user_message)
        
        # Try to parse JSON from response
        try:
            # Find JSON in response
            json_str = response[response.find("{") : response.rfind("}") + 1]
            data = json.loads(json_str)
            judge = JudgeResult(
                score=int(data.get("score", 0)),
                reason=str(data.get("reason", "No reason provided")),
                missing_evidence=data.get("missing_evidence", []),
                spurious_claims=data.get("spurious_claims", []),
            )
        except (json.JSONDecodeError, ValueError):
            # Fallback to simple comparison
            if normalize_answer(example.gold_answer) == normalize_answer(answer):
                judge = JudgeResult(
                    score=1,
                    reason="Answer matches gold answer after normalization.",
                )
            else:
                judge = JudgeResult(
                    score=0,
                    reason=f"Predicted answer does not match gold answer.",
                    missing_evidence=["Accurate answer required"],
                )
        
        return judge, tokens, latency
    
    def reflector(
        self,
        example: QAExample,
        attempt_id: int,
        judge: JudgeResult,
    ) -> tuple[ReflectionEntry, int, float]:
        """Generate reflection using Reflector agent"""
        user_message = f"""Question: {example.question}
Attempt {attempt_id} Answer: (not needed for reflection)
Evaluation Reason: {judge.reason}
Missing Evidence: {', '.join(judge.missing_evidence) if judge.missing_evidence else "None"}

Based on the failure analysis above, what strategy should be tried in the next attempt?
Provide your reflection with the key lesson learned and specific strategy."""
        
        response, tokens, latency = self.call_llm(REFLECTOR_SYSTEM, user_message)
        
        # Parse structured reflection from response
        lines = response.strip().split("\n")
        lesson = response[:200]  # First 200 chars as lesson
        next_strategy = response  # Entire response as strategy
        
        reflection = ReflectionEntry(
            attempt_id=attempt_id,
            failure_reason=judge.reason,
            lesson=lesson,
            next_strategy=next_strategy,
        )
        
        return reflection, tokens, latency


# Global LLM runtime instance
_llm_runtime: Optional[LLMRuntime] = None


def get_llm_runtime(
    model: str = "gpt-4-turbo",
    use_ollama: bool = False,
) -> LLMRuntime:
    """Get or create LLM runtime instance"""
    global _llm_runtime
    
    if _llm_runtime is None:
        _llm_runtime = LLMRuntime(
            model=model,
            use_ollama=use_ollama,
        )
    
    return _llm_runtime


def set_llm_runtime(runtime: LLMRuntime) -> None:
    """Set global LLM runtime instance"""
    global _llm_runtime
    _llm_runtime = runtime
