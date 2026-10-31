from ..models import Analysis

PROMPT = """You are the Code Analysis Agent. Analyze the supplied sampled program and diff once for downstream agents. Explain the program's overall purpose, main functional parts and their responsibilities, how those parts cooperate, and the flow from input to output. Group related files/functions into meaningful architectural parts rather than treating every function or line as an independent learning objective.
For both initial and change reviews, choose 2-4 broad learning objectives about the whole supplied program: its purpose, component responsibilities, cooperation, or end-to-end workflow. Tiny programs may need fewer. Do not turn implementation details, exact function names, particular assignments, numeric constants, floating-point rounding, loop mechanics, or complexity calculations into assessment objectives. A change review should still describe the PR's actual changes and explain how they fit into the wider program in changed_functions and impacts; the quiz itself assesses overall structural understanding.
Cite exact supplied file paths and valid line ranges; evidence may span multiple parts and need not be restricted to changed lines. Separate confirmed facts from potential risks. Be explicit that the supplied files may only be a sample, and do not invent missing components or pretend the sampled code proves the whole repository's architecture. Use the supplied review_type exactly. Return the Analysis schema."""


def analyze(llm, data):
    result = llm.generate(Analysis, PROMPT, data)
    result.review_type = data['review_type']
    result.changed_files = data['changed_files']
    result.limitations = list(dict.fromkeys(result.limitations + data['limitations']))
    return result
