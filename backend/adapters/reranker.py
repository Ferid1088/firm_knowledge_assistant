"""Qwen3-Reranker — causal-LM yes/no scoring (NOT a sequence-classification head).

Qwen3-Reranker-0.6B ships as a causal LM. Relevance is scored by comparing the
logits of the "yes"/"no" tokens after a fixed instruction template, per the
official usage. Loading it via AutoModelForSequenceClassification (CrossEncoder
default) gives a randomly-initialized score head -> meaningless scores.
"""
from __future__ import annotations
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

from backend.config import RERANKER_MODEL_ID, EMBED_MAX_SEQ, RERANKER_MAX_LENGTH, RERANKER_BATCH_SIZE, RERANKER_DEVICE

_PREFIX = (
    "<|im_start|>system\nJudge whether the Document meets the requirements based on "
    "the Query and the Instruct provided. Note that the answer can only be \"yes\" or \"no\".<|im_end|>\n"
    "<|im_start|>user\n"
)
_SUFFIX = "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"
_DEFAULT_INSTRUCTION = "Given a web search query, retrieve relevant passages that answer the query"


class Qwen3Reranker:
    """Causal-LM reranker that scores (query, document) pairs by comparing
    the log-probability of the "yes" token against "no" after a fixed prompt.

    Loaded once and reused across requests via the graph utils singleton.
    """

    def __init__(self, model_id: str = RERANKER_MODEL_ID, device: str = RERANKER_DEVICE, max_length: int = RERANKER_MAX_LENGTH):
        """Load the causal-LM weights and cache the 'yes'/'no' token IDs for scoring."""
        self.tokenizer = AutoTokenizer.from_pretrained(model_id, padding_side="left")
        self.model = AutoModelForCausalLM.from_pretrained(model_id).to(device).eval()
        self.device = device
        self.max_length = min(max_length, EMBED_MAX_SEQ)
        self.token_false_id = self.tokenizer.convert_tokens_to_ids("no")
        self.token_true_id = self.tokenizer.convert_tokens_to_ids("yes")
        self._prefix_ids = self.tokenizer.encode(_PREFIX, add_special_tokens=False)
        self._suffix_ids = self.tokenizer.encode(_SUFFIX, add_special_tokens=False)

    def _format(self, query: str, doc: str) -> str:
        """Wrap query and document in the instruction template expected by Qwen3-Reranker."""
        return f"<Instruct>: {_DEFAULT_INSTRUCTION}\n<Query>: {query}\n<Document>: {doc}"

    @torch.no_grad()
    def predict(self, pairs: list[tuple[str, str]], batch_size: int = RERANKER_BATCH_SIZE) -> list[float]:
        """Score (query, document) pairs; returns probabilities in [0, 1] order-matched to pairs."""
        scores: list[float] = []
        for i in range(0, len(pairs), batch_size):
            batch = pairs[i:i + batch_size]
            texts = [self._format(q, d) for q, d in batch]
            budget = self.max_length - len(self._prefix_ids) - len(self._suffix_ids)
            inputs = self.tokenizer(
                texts, padding=False, truncation="longest_first",
                return_attention_mask=False, max_length=budget,
            )
            for j, ids in enumerate(inputs["input_ids"]):
                inputs["input_ids"][j] = self._prefix_ids + ids + self._suffix_ids
            padded = self.tokenizer.pad(inputs, padding=True, return_tensors="pt")
            padded = {k: v.to(self.device) for k, v in padded.items()}

            logits = self.model(**padded).logits[:, -1, :]
            true_vec = logits[:, self.token_true_id]
            false_vec = logits[:, self.token_false_id]
            stacked = torch.stack([false_vec, true_vec], dim=1)
            log_probs = torch.nn.functional.log_softmax(stacked, dim=1)
            batch_scores = log_probs[:, 1].exp().tolist()
            scores.extend(batch_scores)
        return scores
