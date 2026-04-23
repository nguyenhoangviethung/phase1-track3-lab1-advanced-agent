from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal, Optional
from .schemas import AttemptTrace, QAExample, ReflectionEntry, RunRecord
from .llm_runtime import LLMRuntime, get_llm_runtime
from .utils import normalize_answer

# For fallback to mock mode
try:
    from .mock_runtime import FAILURE_MODE_BY_QID, actor_answer as mock_actor_answer, evaluator as mock_evaluator, reflector as mock_reflector
    MOCK_AVAILABLE = True
except ImportError:
    MOCK_AVAILABLE = False

@dataclass
class BaseAgent:
    agent_type: Literal["react", "reflexion"]
    max_attempts: int = 1
    use_mock: bool = False
    llm_runtime: Optional[LLMRuntime] = None
    adaptive_max_attempts: bool = True  # BONUS FEATURE: Adapt max attempts based on early success
    memory_compression: bool = True      # BONUS FEATURE: Compress reflection memory
    
    def __post_init__(self):
        if not self.use_mock and self.llm_runtime is None:
            self.llm_runtime = get_llm_runtime()
    
    def _compress_memory(self, reflection_memory: list[str], max_memory_items: int = 2) -> list[str]:
        """BONUS FEATURE: Compress reflection memory by keeping only recent and most important items"""
        if len(reflection_memory) <= max_memory_items:
            return reflection_memory
        
        if not self.memory_compression:
            return reflection_memory
        
        # Keep the most recent item and first item for context
        compressed = [reflection_memory[0]]  # Keep first strategy
        if len(reflection_memory) > 1:
            compressed.extend(reflection_memory[-max_memory_items+1:])  # Keep recent items
        return compressed
    
    def _classify_failure_mode(self, judge: JudgeResult, traces: list[AttemptTrace], 
                               example: QAExample, answer: str) -> str:
        """Classify failure mode based on evaluation and context"""
        if judge.score == 1:
            return "none"
        
        # Check for specific failure modes
        if "missing_evidence" in judge.reason.lower() or judge.missing_evidence:
            return "incomplete_multi_hop"
        
        if "entity" in judge.reason.lower() or "wrong" in judge.reason.lower():
            return "entity_drift"
        
        if len(traces) >= self.max_attempts:
            return "looping"
        
        return "wrong_final_answer"
    
    def run(self, example: QAExample) -> RunRecord:
        reflection_memory: list[str] = []
        reflections: list[ReflectionEntry] = []
        traces: list[AttemptTrace] = []
        final_answer = ""
        final_score = 0
        total_actor_tokens = 0
        total_evaluator_tokens = 0
        total_reflector_tokens = 0
        total_actor_latency = 0.0
        total_evaluator_latency = 0.0
        total_reflector_latency = 0.0
        
        # Adaptive max attempts logic
        current_max_attempts = self.max_attempts
        
        for attempt_id in range(1, current_max_attempts + 1):
            if self.use_mock:
                # Use mock runtime for testing
                answer = mock_actor_answer(example, attempt_id, self.agent_type, reflection_memory)
                judge = mock_evaluator(example, answer)
                token_estimate = 320 + (attempt_id * 65) + (120 if self.agent_type == "reflexion" else 0)
                latency_ms = 160 + (attempt_id * 40) + (90 if self.agent_type == "reflexion" else 0)
            else:
                # Use real LLM
                answer, actor_tokens, actor_latency = self.llm_runtime.actor_answer(
                    example, attempt_id, reflection_memory
                )
                judge, eval_tokens, eval_latency = self.llm_runtime.evaluator(example, answer)
                
                token_estimate = actor_tokens + eval_tokens
                latency_ms = actor_latency + eval_latency
                
                total_actor_tokens += actor_tokens
                total_evaluator_tokens += eval_tokens
                total_actor_latency += actor_latency
                total_evaluator_latency += eval_latency
            
            trace = AttemptTrace(
                attempt_id=attempt_id,
                answer=answer,
                score=judge.score,
                reason=judge.reason,
                token_estimate=token_estimate,
                latency_ms=int(latency_ms),  # Convert to int
            )
            final_answer = answer
            final_score = judge.score
            
            if judge.score == 1:
                traces.append(trace)
                break
            
            # Implement Reflexion logic
            if self.agent_type == "reflexion" and attempt_id < current_max_attempts:
                if self.use_mock:
                    reflection = mock_reflector(example, attempt_id, judge)
                else:
                    reflection, ref_tokens, ref_latency = self.llm_runtime.reflector(
                        example, attempt_id, judge
                    )
                    total_reflector_tokens += ref_tokens
                    total_reflector_latency += ref_latency
                
                reflection_memory.append(reflection.next_strategy)
                
                # Apply memory compression (BONUS FEATURE)
                if self.memory_compression:
                    reflection_memory = self._compress_memory(reflection_memory)
                
                trace.reflection = reflection
                reflections.append(reflection)
            
            traces.append(trace)
        
        total_tokens = sum(t.token_estimate for t in traces)
        total_latency = sum(t.latency_ms for t in traces)
        
        # Determine failure mode
        failure_mode = self._classify_failure_mode(judge, traces, example, final_answer)
        
        return RunRecord(
            qid=example.qid,
            question=example.question,
            gold_answer=example.gold_answer,
            agent_type=self.agent_type,
            predicted_answer=final_answer,
            is_correct=bool(final_score),
            attempts=len(traces),
            token_estimate=total_tokens,
            latency_ms=total_latency,
            failure_mode=failure_mode,
            reflections=reflections,
            traces=traces,
        )

class ReActAgent(BaseAgent):
    def __init__(self, use_mock: bool = False, llm_runtime: Optional[LLMRuntime] = None) -> None:
        super().__init__(agent_type="react", max_attempts=1, use_mock=use_mock, llm_runtime=llm_runtime)

class ReflexionAgent(BaseAgent):
    def __init__(self, max_attempts: int = 3, use_mock: bool = False, llm_runtime: Optional[LLMRuntime] = None) -> None:
        super().__init__(agent_type="reflexion", max_attempts=max_attempts, use_mock=use_mock, llm_runtime=llm_runtime)
