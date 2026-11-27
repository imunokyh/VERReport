# VERReport

테스트·정적분석·커버리지 결과를 한 번에 보여주는 **정적 HTML 대시보드 생성기**입니다.
서버 없이 `index.html`을 열기만 하면 되고(Chart.js 로컬 번들, 인터넷 불필요), CI 산출물로 보관하기 좋습니다.

| 도구 | 입력 | 표출 정보 |
|---|---|---|
| Google Test | GTest XML | 통과/실패/스킵, 스위트·모듈·파일·테스트케이스, 실패 메시지 |
| LLVM 커버리지 | `llvm-cov export` JSON | lines / functions / regions / branches, 모듈·파일·함수 |
| CPPCheck | XML v2 | severity·규칙별 위반, 모듈·파일·위반 |
| Lizard | CSV | CCN > 10, 함수 라인수 > 80 위반 함수, 모듈·파일·함수 |

화면: **대시보드**(빌드 정보·전체 PASS/FAIL·도구별 차트/표/"상세 결과 보기") → **도구별 상세**(모듈 → 파일 → 함수 접이식 트리, 검색·필터·정렬).

## 설치

Python 3.10+

```bash
pip install -e .          # 개발: pip install -e ".[dev]"
```

## 사용법

```bash
verreport generate \
  --gtest gtest.xml --llvm-cov llvm-cov.json \
  --cppcheck cppcheck.xml --lizard lizard.csv \
  --build-number 128 --commit "$(git rev-parse HEAD)" --branch main \
  -o report --fail-on-violation
```

- 도구 결과는 **일부만** 줘도 됩니다. 없는 도구는 "NO DATA"로 표시되고 상세 페이지도 만들지 않습니다.
- 또는 설정 파일로: `verreport generate -c samples/verreport.yml -o report` (`python -m verreport ...`도 동일)
- 데모: `verreport generate -c samples/verreport.yml -o report` 후 `report/index.html` 열기

### 입력 파일 만들기

```bash
# Google Test
./unit_tests --gtest_output=xml:gtest.xml

# LLVM coverage (clang -fprofile-instr-generate -fcoverage-mapping 으로 빌드)
LLVM_PROFILE_FILE=cov-%p.profraw ./unit_tests
llvm-profdata merge -sparse cov-*.profraw -o cov.profdata
llvm-cov export ./unit_tests -instr-profile=cov.profdata -format=text > llvm-cov.json

# CPPCheck (XML은 stderr로 출력됩니다)
cppcheck --xml --xml-version=2 src 2> cppcheck.xml

# Lizard
lizard src --csv > lizard.csv
```

> llvm-cov의 파일 경로는 보통 절대경로입니다. 모듈 이름을 짧게 하려면 설정의 `source_root`에 프로젝트 루트를 지정하세요.

### 옵션

| 옵션 | 설명 |
|---|---|
| `--gtest` `--llvm-cov` `--cppcheck` `--lizard` | 도구 결과 파일. `--gtest`는 **여러 파일/glob**을 받아 하나로 합칩니다 (`--gtest unit/*.xml integration/*.xml`). 설정 파일에서는 `inputs.gtest`에 리스트로 지정 |
| `-o, --out DIR` | 출력 디렉터리 (기본 `report`) |
| `-c, --config YAML` | 설정 파일 |
| `--project` `--build-number` `--build-time` `--commit` `--branch` | 빌드 정보. 미지정 시 환경변수(`BUILD_NUMBER`/`GITHUB_RUN_NUMBER`, `GIT_COMMIT`/`GITHUB_SHA`, `GIT_BRANCH`/`GITHUB_REF_NAME`), 빌드 시각은 현재 시각 |
| `--ccn-limit` `--length-limit` `--coverage-target` | 임계값 덮어쓰기 (기본 10 / 80 / 80%) |
| `--fail-on-violation` | 전체 판정이 FAIL이면 종료 코드 1 |

설정 우선순위: **CLI > 설정 파일 > 환경변수 > 기본값**. 설정 파일 항목은 [`samples/verreport.yml`](samples/verreport.yml) 참고.

### 종료 코드

| 코드 | 의미 |
|---|---|
| 0 | 리포트 생성 성공 |
| 1 | 리포트는 생성됐지만 검증 FAIL (`--fail-on-violation`일 때만) |
| 2 | 사용법·설정·입력 오류. 읽을 수 있는 도구가 하나라도 있으면 리포트는 생성됨 |

## 판정 기준

| 도구 | PASS 조건 |
|---|---|
| Google Test | 실패한 테스트 0건 (스킵은 무시) |
| 커버리지 | line 커버리지 ≥ 목표 (기본 80%). llvm-cov 출력에 MC/DC가 있으면 함께 표시 (판정에는 미반영) |
| CPPCheck | `error` severity 0건 (warning/style 등은 표시만) |
| Lizard | CCN > 10 또는 길이 > 80 라인인 함수 0개 (경계값은 위반 아님) |

전체 판정은 **결과가 있는 도구가 모두 PASS**일 때 PASS입니다. 도구가 하나도 없으면 리포트를 만들지 않습니다.

## 모듈 구분

기본값은 소스 경로의 앞 `module_depth`(기본 2)단계 디렉터리입니다 (`src/core/parser.cc` → `src/core`).
`source_root`로 접두 경로를 제거하거나 `module_map`으로 경로 접두어 → 모듈명을 직접 지정할 수 있습니다 (가장 긴 접두어 우선).

## CI 연동

- GitHub Actions: [`examples/ci/github-actions.yml`](examples/ci/github-actions.yml)
- Jenkins: [`examples/ci/Jenkinsfile`](examples/ci/Jenkinsfile)

## 대용량 리포트

합성 데이터(파일 3,000개, 함수/테스트/위반 합계 약 45,000행 × 4개 도구)로 측정했습니다.

| 항목 | 결과 |
|---|---|
| 리포트 생성 시간 | 약 6초 (입력 합계 17MB) |
| 상세 페이지 크기 | 8~15MB (들여쓰기 제거 적용 후) |
| 상세 페이지 로드 (Edge) | 약 3~5초, DOM 노드 34만~39만 |
| 검색·필터 반응 | 약 80ms |

수백 파일 규모에서는 체감 지연이 거의 없습니다. 파일 수천 개 이상에서 로드가 부담되면 `module_depth`/`source_root` 설정과
무관하게 입력을 모듈 단위로 나눠 여러 리포트로 생성하는 것을 권장합니다. (행을 JSON으로 임베드해 펼칠 때 렌더링하는 방식은 아직 미적용)

## 개발

```bash
pip install -e ".[dev]"
python -m pytest
```

```
src/verreport/
  cli.py            CLI (generate)
  config.py         설정/임계값, YAML 로더
  models.py         공통 데이터 모델
  parsers/          gtest · llvmcov · cppcheck · lizard 파서
  analysis/         모듈→파일→항목 그룹핑, 도구별 집계, 판정
  render/           Jinja2 템플릿, 리포트 생성
  static/           CSS, JS, Chart.js
samples/            각 도구 결과 예시 + 설정 예시
tests/              pytest
```

새 도구를 추가하려면 `models.py`에 모델 → `parsers/`에 파서 → `analysis/summary.py`에 집계 → `render/templates/`에 페이지를 추가하면 됩니다.
