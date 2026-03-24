"""
module3/evaluators/llm_judge.py
================================
LLM-as-judge evaluation implementation.

Uses Claude Opus (different from agent's Sonnet) to evaluate agent outputs
against defined criteria. This is the core evaluation pattern for Module 3.
"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from module3.config.models import get_judge_model


# ---------------------------------------------------------------------------
# Judge Prompt Templates
# ---------------------------------------------------------------------------

JUDGE_PROMPT_TEMPLATE = """You are an expert evaluator for AI agent outputs. Your job is to assess the quality of an agent's response against defined criteria.

## Task
{task_description}

## Agent's Output
{agent_output}

## Reference Answer (if available)
{reference_answer}

## Evaluation Criteria

{criteria}

## Scoring Rubric

For each criterion, provide a score from 0-100:
- 90-100: Excellent - Exceeds expectations
- 70-89: Good - Meets expectations with minor issues
- 50-69: Acceptable - Meets basic requirements but has notable gaps
- 30-49: Poor - Significant issues or missing elements
- 0-29: Very Poor - Does not meet requirements

## Response Format

Provide your evaluation as a JSON object:

```json
{{
  "scores": {{
    "criterion_1": 85,
    "criterion_2": 92,
    ...
  }},
  "overall_score": 88,
  "rationale": {{
    "criterion_1": "Brief explanation for this score",
    "criterion_2": "Brief explanation for this score",
    ...
  }},
  "strengths": ["Strength 1", "Strength 2", ...],
  "weaknesses": ["Weakness 1", "Weakness 2", ...],
  "recommendations": ["Recommendation 1", "Recommendation 2", ...]
}}
```

Be thorough but concise. Focus on specific, actionable feedback.
"""


# ---------------------------------------------------------------------------
# LLM-as-Judge Function
# ---------------------------------------------------------------------------

def create_judge_prompt(
    task_description: str,
    agent_output: str,
    criteria: dict[str, str],
    reference_answer: str | None = None,
) -> str:
    """
    Create a judge prompt for evaluating agent output.

    Parameters
    ----------
    task_description : str
        Description of the task the agent was asked to perform.
    agent_output : str
        The agent's actual output.
    criteria : dict
        Evaluation criteria as {criterion_name: description}.
    reference_answer : str, optional
        Expected or reference answer for comparison.

    Returns
    -------
    str
        Formatted judge prompt.
    """
    # Format criteria
    criteria_text = "\n".join([
        f"**{name}**: {desc}"
        for name, desc in criteria.items()
    ])
    
    # Format reference answer
    ref_text = reference_answer if reference_answer else "Not provided"
    
    return JUDGE_PROMPT_TEMPLATE.format(
        task_description=task_description,
        agent_output=agent_output,
        reference_answer=ref_text,
        criteria=criteria_text,
    )


def evaluate_with_llm_judge(
    task_description: str,
    agent_output: str,
    criteria: dict[str, str],
    reference_answer: str | None = None,
    region: str | None = None,
    verbose: bool = True,
) -> dict[str, Any]:
    """
    Evaluate agent output using LLM-as-judge pattern.

    Uses Claude Opus (different from agent's Sonnet) for unbiased evaluation.

    Parameters
    ----------
    task_description : str
        Description of the task.
    agent_output : str
        Agent's output to evaluate.
    criteria : dict
        Evaluation criteria as {criterion_name: description}.
    reference_answer : str, optional
        Expected answer for comparison.
    region : str, optional
        AWS region for Bedrock.
    verbose : bool
        Print evaluation progress.

    Returns
    -------
    dict
        Evaluation results with scores, rationale, and recommendations.

    Example
    -------
    >>> criteria = {
    ...     "completeness": "All required CDK resources are included",
    ...     "best_practices": "Follows AWS and CDK best practices",
    ...     "security": "Proper security configurations",
    ... }
    >>> result = evaluate_with_llm_judge(
    ...     task_description="Generate VPC CDK stack",
    ...     agent_output=cdk_code,
    ...     criteria=criteria,
    ... )
    >>> print(result["overall_score"])
    """
    # Get judge model (Claude Opus, temperature=0.0)
    judge_model = get_judge_model(region=region)
    
    # Create prompt
    prompt_text = create_judge_prompt(
        task_description=task_description,
        agent_output=agent_output,
        criteria=criteria,
        reference_answer=reference_answer,
    )
    
    # Create chain
    prompt = ChatPromptTemplate.from_messages([
        ("user", prompt_text),
    ])
    chain = prompt | judge_model | StrOutputParser()
    
    if verbose:
        print("  [LLM Judge] Evaluating agent output...")
        print(f"  [Criteria] {len(criteria)} evaluation criteria")
    
    # Invoke judge
    response = chain.invoke({})
    
    # Parse JSON response
    try:
        # Extract JSON from response
        if "```json" in response:
            json_str = response.split("```json")[1].split("```")[0].strip()
        elif "```" in response:
            json_str = response.split("```")[1].split("```")[0].strip()
        else:
            json_str = response.strip()
        
        result = json.loads(json_str)
        
        if verbose:
            print(f"  [Overall Score] {result.get('overall_score', 'N/A')}/100")
            print(f"  [Strengths] {len(result.get('strengths', []))}")
            print(f"  [Weaknesses] {len(result.get('weaknesses', []))}")
        
        return result
        
    except (json.JSONDecodeError, KeyError) as e:
        if verbose:
            print(f"  [Warning] Failed to parse judge response: {e}")
        
        # Return fallback result
        return {
            "scores": {},
            "overall_score": 0,
            "rationale": {},
            "strengths": [],
            "weaknesses": ["Failed to parse evaluation response"],
            "recommendations": ["Retry evaluation"],
            "raw_response": response,
            "error": str(e),
        }


# ---------------------------------------------------------------------------
# Batch Evaluation
# ---------------------------------------------------------------------------

def evaluate_batch(
    evaluations: list[dict[str, Any]],
    region: str | None = None,
    verbose: bool = False,
) -> list[dict[str, Any]]:
    """
    Evaluate multiple agent outputs in batch.

    Parameters
    ----------
    evaluations : list of dict
        List of evaluation specs, each with:
        - task_description: str
        - agent_output: str
        - criteria: dict
        - reference_answer: str (optional)
    region : str, optional
        AWS region for Bedrock.
    verbose : bool
        Print progress for each evaluation.

    Returns
    -------
    list of dict
        Evaluation results for each output.

    Example
    -------
    >>> evaluations = [
    ...     {
    ...         "task_description": "Generate VPC stack",
    ...         "agent_output": vpc_code,
    ...         "criteria": vpc_criteria,
    ...     },
    ...     {
    ...         "task_description": "Generate RDS stack",
    ...         "agent_output": rds_code,
    ...         "criteria": rds_criteria,
    ...     },
    ... ]
    >>> results = evaluate_batch(evaluations)
    """
    results = []
    
    for i, eval_spec in enumerate(evaluations):
        if verbose:
            print(f"\n[Batch Evaluation {i+1}/{len(evaluations)}]")
        
        result = evaluate_with_llm_judge(
            task_description=eval_spec["task_description"],
            agent_output=eval_spec["agent_output"],
            criteria=eval_spec["criteria"],
            reference_answer=eval_spec.get("reference_answer"),
            region=region,
            verbose=verbose,
        )
        
        results.append({
            **eval_spec,
            "evaluation": result,
        })
    
    return results
