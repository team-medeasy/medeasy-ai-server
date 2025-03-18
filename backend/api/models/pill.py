from pydantic import BaseModel, Field, validator
from typing import Optional, List, Union

class PillBase(BaseModel):
    """
    약품 기본 모델.
    - item_seq: 약품 고유번호.
    - print_front, print_back: 약품 인쇄 텍스트.
    - drug_shape: 약품의 모양.
    - color_classes: 약품의 색상. 단일 색상일 경우 문자열, 다중 색상일 경우 리스트.
    - mark_code_front_anal, mark_code_back_anal: 분석된 마크 코드 (쉼표 구분 문자열을 리스트로 변환).
    """
    item_seq: str = Field(..., title="약품 고유번호")
    print_front: Optional[str] = Field(None, title="정면 프린트")
    print_back: Optional[str] = Field(None, title="뒷면 프린트")
    drug_shape: str = Field(..., title="약품 모양")
    color_classes: Union[str, List[str]] = Field(..., title="약품 색상")

    mark_code_front_anal: Optional[Union[str, List[str]]] = Field(
        None, title="분석된 정면 마크 코드", description="쉼표로 구분된 문자열을 리스트로 변환"
    )
    mark_code_back_anal: Optional[Union[str, List[str]]] = Field(
        None, title="분석된 뒷면 마크 코드", description="쉼표로 구분된 문자열을 리스트로 변환"
    )

    @validator("color_classes", pre=True)
    def ensure_color_list(cls, value):
        """색상이 단일 문자열이면 리스트로 변환 (예: '하양' -> ['하양'])"""
        if isinstance(value, str):
            return [value.strip()]
        # 리스트인 경우, 각 요소에 대해 strip() 적용
        if isinstance(value, list):
            return [v.strip() for v in value if isinstance(v, str)]
        return value

    @validator("mark_code_front_anal", "mark_code_back_anal", pre=True)
    def split_mark_codes(cls, value):
        """
        마크 코드가 쉼표(,)로 구분된 문자열이면 리스트로 변환.
        만약 이미 리스트면 그대로 반환.
        """
        if isinstance(value, str):
            # 공백 제거 후, 빈 문자열은 무시
            codes = [code.strip() for code in value.split(",") if code.strip()]
            return codes if len(codes) > 1 else (codes[0] if codes else None)
        return value

class PillCreate(PillBase):
    """약품 추가 요청 모델."""
    embedding: Optional[List[float]] = Field(None, title="벡터 임베딩", description="이미지 분석 등에서 생성된 임베딩 벡터")

class PillResponse(PillBase):
    """약품 검색 응답 모델."""
    id: str = Field(..., title="MongoDB Object ID")
    embedding: Optional[List[float]] = Field(None, title="벡터 임베딩")

    class Config:
        orm_mode = True  # ORM 연동 지원