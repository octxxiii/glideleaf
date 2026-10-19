# Glideleaf: 출처 및 재배포 안내

Glideleaf는 https://github.com/fuba/winuc 의 수정판입니다.
원본 Copyright (c) 2026 fuba 및 MIT 라이선스 전문은 LICENSE에 보존합니다.
추가·수정한 프로젝트 코드도 MIT로 제공합니다. 변경 내역은 LOCAL_CHANGES.md에 있습니다.
원저자 또는 Apple의 공식 제품이나 보증을 의미하지 않습니다.

## 소스 코드 공개

원본 MIT 고지와 LICENSE를 유지하세요. `.venv`, 사용자 설정, 페어링 키,
로그, 펌웨어 및 외부 실행 파일은 소스 저장소에 포함하지 않습니다.

## 실행 파일에 포함되는 구성 요소

아래는 직접 의존성입니다. 전체 전이 의존성·버전·동봉 라이선스는
빌드 시 생성되는 `licenses/dependencies.json` 및 각 하위 폴더를 확인하세요.

| 구성 요소 | 라이선스 | 출처 |
| --- | --- | --- |
| Bumble | Apache-2.0 및 포함 고지 | https://github.com/google/bumble |
| pystray | LGPL-3.0 | https://github.com/moses-palmer/pystray |
| libusb1 Python 바인딩 | LGPL-2.1-or-later | https://github.com/vpelletier/python-libusb1 |
| libusb-package Python 패키지 | Apache-2.0 | https://github.com/pyusb/libusb-package |
| libusb 네이티브 DLL | LGPL-2.1-or-later | https://github.com/libusb/libusb |
| Pillow 및 포함 라이브러리 | MIT-CMU 및 포함 고지 | https://github.com/python-pillow/Pillow |

`libusb-package`의 Apache 라이선스가 포함 DLL의 LGPL을 대체하지 않습니다.
LGPL 구성 요소의 해당 버전 소스 제공, 수정본 표시, 교체·수정 및 디버깅에 필요한
조건을 실제 배포 방식에 맞게 충족해야 합니다. 라이선스 링크만 적는 것으로
실행 파일 재배포 의무가 모두 충족되는 것은 아닙니다.
Python과 Tcl/Tk 및 Pillow wheel 등에 포함된 네이티브 라이브러리 고지도 보존해야 합니다.
라이선스 수집기는 Python 패키지 고지를 모으는 도구이며 법적 적합성 판정기는 아닙니다.

## 선택 구성 요소

- 자체 동글 설치: Windows 내장 WinUSB 및 시스템 설치 API를 사용합니다.
  Zadig/libwdi/wdi-simple 실행 파일이나 라이브러리는 현재 앱에 포함하거나
  다운로드하지 않습니다. 이전 개발판의 캐시도 사용하지 않습니다.
  기존 winuc/licenses의 GPL/LGPL 전문은 이전 개발판 고지 이력을 위해 보존합니다.
  자체 INF 소스는 프로젝트 MIT 코드이며 실제 배포 패키지는 Windows의
  서명·신뢰 검증을 통과해야 합니다. docs/DRIVER_TOOL.md를 확인하세요.
- Realtek 펌웨어: MIT 프로젝트 코드에 포함되지 않습니다. 실제 다운로드한 파일에
  적용되는 펌웨어 라이선스와 배포 조건을 확인하고 고지문을 함께 제공해야 합니다.
  https://gitlab.com/kernel-firmware/linux-firmware

공개 소스와 별개로, 바이너리 릴리스 전에 정확한 빌드 산출물의 구성 요소와
라이선스/대응 소스 제공 방식을 검토해야 합니다. 현재 문서는 상표 사용 가능 여부나
특허·인증까지 확인했다는 뜻이 아닙니다.
