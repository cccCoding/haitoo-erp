"""货盘标题正文规则；链接编号另计，不影响普通商品草稿标题。"""

MINIMUM = 25
MAXIMUM = 230
TARGET_MINIMUM = 180
TARGET_MAXIMUM = 200
KEYWORD_BUDGET = 170
MAX_ATTEMPTS = 4


def correction_feedback(reason, length):
    limits = f'target {TARGET_MINIMUM}-{TARGET_MAXIMUM} characters; hard limit {MINIMUM}-{MAXIMUM}'
    if reason == 'overlong':
        return (f'Previous title has {length} characters, exceeding the hard limit by {length - MAXIMUM}. '
                f'Compress to {limits}. Remove repetition and unnecessary wording; preserve every required phrase.')
    if reason == 'short':
        return (f'Previous title has {length} characters, {MINIMUM - length} below the minimum. '
                f'Expand using confirmed attributes only to {limits}. Preserve every required phrase.')
    return (f'The title is {"empty" if reason == "empty" else "not a string"}. '
            f'Return a JSON object with a nonempty string title; {limits}.')
