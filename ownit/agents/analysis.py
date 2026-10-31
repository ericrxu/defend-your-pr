from ..models import Analysis

PROMPT = """You are the Code Analysis Agent. Analyze the supplied sampled code and diff once for downstream agents. For initial reviews identify architecture, interactions, functions, algorithms, APIs, data flow, assumptions and security. For change reviews identify NEW additions and modified behavior, including new subsystems. Existing architecture may explain context but is not an assessment topic. Each change-review learning objective MUST concern code introduced or modified by THIS diff, with evidence on the added/modified head lines; never choose an unchanged function's existing behavior as an objective. Prefer 2-4 focused, practical objectives for a small PR; use more only when distinct changes warrant them. Do not pad the objective count with original repository concepts. Cite exact supplied file paths and valid line ranges. Separate confirmed facts from potential risks. Be explicit about missing context. Use the supplied review_type exactly. Changed paths can include deleted files but evidence must cite available head files. Return the Analysis schema."""


def analyze(llm, data):
    result = llm.generate(Analysis, PROMPT, data)
    result.review_type = data['review_type']
    result.changed_files = data['changed_files']
    result.limitations = list(dict.fromkeys(result.limitations + data['limitations']))
    return result
