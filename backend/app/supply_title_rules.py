"""货盘标题正文规则；链接编号另计，不影响普通商品草稿标题。"""
import unicodedata

MINIMUM = 25
MAXIMUM = 230
TARGET_MINIMUM = 180
TARGET_MAXIMUM = 200
KEYWORD_BUDGET = 170
MAX_ATTEMPTS = 4
COMPRESSION_STEPS = ((150, 190), (120, 180))


def content_characters(phrases):
    """按规范化词组去重，连同组间空格计算内容预算。"""
    unique = {}
    for phrase in phrases:
        phrase = ' '.join(unicodedata.normalize('NFKC', phrase).split())
        if phrase:
            unique.setdefault(phrase.casefold(), phrase)
    return len(' '.join(unique.values()))


def compression_budget(level, content, protected, previous_length):
    if level > len(COMPRESSION_STEPS):
        return protected
    ceiling, target = COMPRESSION_STEPS[level - 1]
    return max(protected, min(content, ceiling, content * target // previous_length))


def compression_feedback(reason, length):
    if reason == 'overlong':
        return (f'Previous title has {length} characters, exceeding the hard limit by {length - MAXIMUM}. '
                'Rewrite around the retained required_phrases using the reduced keyword_budget. '
                f'Prefer {TARGET_MINIMUM}-{TARGET_MAXIMUM}, accepting any complete title within {MINIMUM}-{MAXIMUM}. '
                'Remove repetition and optional descriptions.')
    return (f'The title is {"below the minimum" if reason == "short" else "empty" if reason == "empty" else "not a string"}. '
            f'Return a complete factual string title within {MINIMUM}-{MAXIMUM} characters; '
            'do not expand using unused facts or restore omitted optional phrases.')


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
