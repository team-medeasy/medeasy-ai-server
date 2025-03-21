from typing import List

def generate_character_variations(text: str) -> List[str]:
    """
    OCR이나 이미지 인식에서 흔히 혼동되는 유사 문자 변형 생성
    - 숫자 ↔ 알파벳
    - 알파벳 ↔ 유사한 알파벳
    - 자주 혼동되는 문자쌍(예: '73' → 'EL')
    """
    if not text:
        return []

    # 단일 문자 유사 매핑
    similar_chars = {
        '1': ['I', 'l', '|'],
        'I': ['1', 'l'],
        'l': ['1', 'I'],
        '0': ['O', 'D'],
        'O': ['0', 'D'],
        'o': ['0'],
        '8': ['B'],
        'B': ['8'],
        '5': ['S'],
        'S': ['5'],
        '2': ['Z'],
        'Z': ['2', 'N'],
        '6': ['G'],
        'G': ['6'],
        '3': ['E'],
        'E': ['3'],
        '4': ['A'],
        'A': ['4'],
        '7': ['T', 'Y'],
        'T': ['7'],
        '9': ['g', 'q'],
        'L': ['I', '1'],
        '|': ['1', 'I']
    }

    # 문자쌍 패턴 기반 유사 변환
    pattern_map = {
        '73': ['EL', 'EI'],
        '52': ['SZ'],
        '25': ['ZS'],
        'Z5': ['ZS'],
        '8B': ['BB'],
        'I0': ['ID', 'IO'],
        '1O': ['IO'],
        '0O': ['OO'],
        'O0': ['00'],
        'B8': ['88'],
    }

    variations = set()

    # 1. 단일 문자 치환
    for i, char in enumerate(text):
        if char in similar_chars:
            for alt in similar_chars[char]:
                new = text[:i] + alt + text[i+1:]
                variations.add(new)

    # 2. 문자쌍 패턴 치환
    for i in range(len(text) - 1):
        pair = text[i:i+2]
        if pair in pattern_map:
            for alt in pattern_map[pair]:
                new = text[:i] + alt + text[i+2:]
                variations.add(new)

    # 3. 숫자/문자 전체 치환
    if any(c.isdigit() for c in text) and any(c.isalpha() for c in text):
        alpha_only = ''.join(
            'O' if c == '0' else 'I' if c == '1' else 'S' if c == '5' else 
            'Z' if c == '2' else 'B' if c == '8' else 
            'E' if c == '3' else 'A' if c == '4' else 
            'T' if c == '7' else c
            for c in text
        )
        variations.add(alpha_only)

        num_only = ''.join(
            '0' if c.upper() == 'O' else '1' if c.upper() == 'I' else '5' if c.upper() == 'S' else 
            '2' if c.upper() == 'Z' else '8' if c.upper() == 'B' else '3' if c.upper() == 'E' else 
            '4' if c.upper() == 'A' else '7' if c.upper() == 'T' else c
            for c in text
        )
        variations.add(num_only)

    # 중복 제거 및 원본 제거
    variations.discard(text)

    # 최대 10개 반환
    return list(variations)[:10]
