from ..models import Analysis

PROMPT = """You are the Code Analysis Agent. Analyze the supplied sampled code and diff once for downstream agents. For initial reviews identify architecture, interactions, functions, algorithms, APIs, data flow, assumptions and security. For change reviews emphasize behavioral differences, affected functions, downstream dependencies, performance and regressions. Analyze newly introduced subsystems structurally as well. Identify 3-7 important learning objectives (fewer for trivial docs), with exact supplied file paths and valid line ranges. Separate confirmed facts from potential risks. Be explicit about missing context. Use the supplied review_type exactly. Changed paths can include deleted files but evidence must cite available head files. Return the Analysis schema."""


def analyze(llm, data):
    result = llm.generate(Analysis, PROMPT, data)
    result.review_type = data['review_type']
    result.changed_files = data['changed_files']
    result.limitations = list(dict.fromkeys(result.limitations + data['limitations']))
    return result
