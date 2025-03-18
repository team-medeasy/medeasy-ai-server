# backend/search/transform.py

from typing import List

def generate_character_variations(text: str) -> List[str]:
    """
    유사 문자 변형 생성 (예: 1 ↔ I, 0 ↔ O, B ↔ 8 등)
    
    Args:
        text: 원본 텍스트
        
    Returns:
        변형된 텍스트 목록 (최대 8개)
    """
    if not text:
        return []
        
    # 유사 문자 매핑
    similar_chars = {
        '1': ['I', 'l'],
        'I': ['1', 'l'],
        'l': ['1', 'I'],
        '0': ['O', 'o'],
        'O': ['0', 'o'],
        'o': ['0', 'O'],
        '8': ['B'],
        'B': ['8'],
        '5': ['S'],
        'S': ['5'],
        '2': ['Z'],
        'Z': ['2'],
        '6': ['G'],
        'G': ['6'],
    }
    
    variations = []
    
    # 1. 각 위치에서 한 문자만 변경하는 단일 변경 변형
    for i, char in enumerate(text):
        if char in similar_chars:
            for similar_char in similar_chars[char]:
                new_text = text[:i] + similar_char + text[i+1:]
                variations.append(new_text)
    
    # 2. 자주 혼동되는 문자 쌍에 대해 두 문자 변경 (최대 2개 문자 조합)
    common_confusions = [('1', '0'), ('I', 'O'), ('1', '8'), ('I', 'B'), ('5', '2'), ('S', 'Z')]
    for i in range(len(text) - 1):
        char_pair = text[i:i+2]
        for conf_pair in common_confusions:
            if char_pair[0] == conf_pair[0] and char_pair[1] == conf_pair[1]:
                for alt1 in similar_chars.get(conf_pair[0], []):
                    for alt2 in similar_chars.get(conf_pair[1], []):
                        new_text = text[:i] + alt1 + alt2 + text[i+2:]
                        variations.append(new_text)
    
    # 3. 약품에서 자주 발생하는 특수 변형 추가
    special_variations = []
    if any(c.isdigit() for c in text) and any(c.isalpha() for c in text):
        # 모든 숫자를 알파벳으로 변경
        alpha_only = ''.join(
            'O' if c == '0' else 'I' if c == '1' else 'S' if c == '5' else 
            'Z' if c == '2' else 'B' if c == '8' else c for c in text
        )
        if alpha_only != text:
            special_variations.append(alpha_only)
        # 모든 알파벳을 숫자로 변경
        num_only = ''.join(
            '0' if c.upper() == 'O' else '1' if c.upper() == 'I' else '5' if c.upper() == 'S' else 
            '2' if c.upper() == 'Z' else '8' if c.upper() == 'B' else c for c in text
        )
        if num_only != text:
            special_variations.append(num_only)
    
    # 중복 제거 및 원본 텍스트 제외
    unique_variations = list(set(variations + special_variations))
    if text in unique_variations:
        unique_variations.remove(text)
    
    # 변형 개수를 최대 8개로 제한
    return unique_variations[:8]
