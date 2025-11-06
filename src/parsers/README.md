# PDF Parsing Module

LH 공공임대주택 공고문 PDF 파싱 시스템입니다. 복잡한 표 구조와 계층적 구조를 정확하게 추출합니다.

## 특징

- **3단계 하이브리드 파싱**: PyMuPDF + Camelot + pdfplumber 조합
- **계층 구조 인식**: 번호, 글머리 기호, 들여쓰기 기반 섹션 감지
- **표 추출**: 중첩 표, 다중 페이지 표 지원
- **한국어 문서 최적화**: 한글 제목 패턴 인식

## 아키텍처

### 1. Layout Analyzer (PyMuPDF)
- 빠른 레이아웃 분석
- 텍스트 블록 좌표 추출
- 표 영역 탐지

**파일**: [layout_analyzer.py](./layout_analyzer.py)

### 2. Table Extractor (Camelot)
- 정밀한 표 추출
- `lattice` 모드: 선 기반 표 감지
- `stream` 모드: 공백 기반 표 감지
- 다중 페이지 표 병합

**파일**: [table_extractor.py](./table_extractor.py)

### 3. Hierarchy Parser (pdfplumber)
- 정밀한 텍스트 추출
- 한국어 제목 패턴 인식:
  - `1.`, `2.` (숫자)
  - `3-1.`, `3-2.` (하위 숫자)
  - `가.`, `나.` (한글)
  - `■`, `▶` (기호)
- 들여쓰기 기반 계층 감지

**파일**: [hierarchy_parser.py](./hierarchy_parser.py)

### 4. LH PDF Parser (통합)
위 3개 파서를 통합하여 최종 문서 구조 생성

**파일**: [lh_pdf_parser.py](./lh_pdf_parser.py)

## 사용법

### 기본 사용

```python
from pathlib import Path
from src.parsers import LHPDFParser

# 파서 생성
parser = LHPDFParser()

# PDF 파싱
pdf_path = Path("announcement.pdf")
document = parser.parse(pdf_path)

# 결과 확인
print(f"총 섹션 수: {document.metadata['total_sections']}")
print(f"총 표 수: {document.metadata['total_tables']}")

# 섹션 순회
for section in document.sections:
    print(f"[Level {section.level}] {section.title}")
    print(f"  - 내용: {len(section.content)} 블록")
    print(f"  - 표: {len(section.tables)} 개")
    print(f"  - 하위섹션: {len(section.children)} 개")
```

### 예제 스크립트

```bash
# 단일 PDF 파싱
poetry run python examples/parse_lh_pdf.py path/to/pdf

# 출력 예시:
# ================================================================================
# Document: 25.09.29인천남부권행복주택예비입주자모집.pdf
# ================================================================================
# Total sections: 94
# Total tables: 47
#
# --------------------------------------------------------------------------------
# Document Structure:
# --------------------------------------------------------------------------------
#
# [Level 1] 1. 공급규모·공급대상 및 임대조건
#   Content: 신청자격 주택형...
#   Table 1: 8 rows × 9 columns (page 0)
#   [Level 2] 1-1. 공급대상
#   [Level 2] 1-2. 임대조건
```

## 데이터 구조

### Document
```python
@dataclass
class Document:
    source_path: Path              # PDF 파일 경로
    sections: List[Section]        # 최상위 섹션 리스트
    metadata: Dict[str, Any]       # 메타데이터
```

### Section
```python
@dataclass
class Section:
    level: int                     # 계층 레벨 (1=최상위)
    title: str                     # 섹션 제목
    bbox: Optional[BoundingBox]    # 위치 정보
    content: List[str]             # 텍스트 내용
    children: List[Section]        # 하위 섹션
    tables: List[TableData]        # 포함된 표
    metadata: Dict[str, Any]       # 메타데이터
```

### TableData
```python
@dataclass
class TableData:
    dataframe: pd.DataFrame        # 표 데이터
    bbox: BoundingBox              # 위치 정보
    page: int                      # 페이지 번호
    caption: Optional[str]         # 표 제목
    metadata: Dict[str, Any]       # 메타데이터 (정확도 등)
```

### BoundingBox
```python
@dataclass
class BoundingBox:
    x0: float                      # 좌측 X
    y0: float                      # 상단 Y
    x1: float                      # 우측 X
    y1: float                      # 하단 Y
    page: int                      # 페이지 번호
```

## 파싱 프로세스

1. **레이아웃 분석** (PyMuPDF)
   - 각 페이지의 텍스트 블록 추출
   - 정렬 기반 표 영역 탐지

2. **표 추출** (Camelot)
   - Lattice 모드: 테두리 있는 표
   - Stream 모드: 테두리 없는 표
   - 중복 제거 및 정확도 필터링 (50% 이상)

3. **계층 구조 파싱** (pdfplumber)
   - 표 영역 제외한 텍스트 추출
   - 제목 패턴 매칭
   - 들여쓰기 기반 레벨 감지
   - 부모-자식 관계 구축

4. **표 병합**
   - 연속 페이지 표 병합
   - 섹션에 표 할당

5. **문서 생성**
   - 최종 Document 객체 생성
   - 메타데이터 추가

## 테스트

```bash
# 유닛 테스트 실행
poetry run pytest tests/parsers/ -v

# 특정 테스트만 실행
poetry run pytest tests/parsers/test_lh_pdf_parser.py::TestLHPDFParser::test_parse_integration -v
```

## 의존성

```toml
[tool.poetry.dependencies]
pymupdf = "^1.24.0"           # 레이아웃 분석
camelot-py = "^0.11.0"        # 표 추출
pdfplumber = "^0.11.0"        # 텍스트 추출
pandas = "^2.2.0"             # 데이터 처리
opencv-python = "^4.9.0"      # 이미지 처리 (Camelot 의존성)
```

## 성능

테스트 결과 (34페이지 LH 공고문):

- **파싱 시간**: ~10초
- **추출된 섹션**: 94개
- **추출된 표**: 47개
- **계층 깊이**: 최대 3단계

## 알려진 제약사항

1. **Ghostscript 필요**: Camelot의 lattice 모드는 Ghostscript가 필요합니다
   - 설치: `brew install ghostscript` (macOS)
   - Stream 모드만으로도 대부분의 표 추출 가능

2. **복잡한 셀 병합**: 극도로 복잡한 셀 병합은 정확도가 떨어질 수 있습니다

3. **이미지 내 텍스트**: 이미지로 된 텍스트는 추출되지 않습니다 (OCR 필요)

## 향후 개선 사항

- [ ] OCR 통합 (이미지 텍스트 추출)
- [ ] 더 정교한 표 셀 병합 처리
- [ ] 섹션-표 매칭 정확도 향상
- [ ] 병렬 처리를 통한 성능 개선
- [ ] PDF 메타데이터 추출 (작성자, 날짜 등)

## 참고 문서

- [PyMuPDF Documentation](https://pymupdf.readthedocs.io/)
- [Camelot Documentation](https://camelot-py.readthedocs.io/)
- [pdfplumber Documentation](https://github.com/jsvine/pdfplumber)
