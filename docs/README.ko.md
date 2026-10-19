# Glideleaf — Windows 마우스·키보드를 iPad에서도

Glideleaf는 PC의 마우스와 키보드 입력을 Bluetooth LE로 iPad에 전달하는 오픈소스
Windows 앱입니다. 지정한 화면 가장자리를 밀면 iPad로 제어가 넘어가며, 반대로
밀거나 **Ctrl+Alt+Q**를 누르면 Windows로 돌아옵니다. iPad에는 별도 앱이 필요 없습니다.

**호환되는 전용 USB 블루투스 동글이 필요합니다.** WinUSB로 전환한 동글은
이어폰·게임패드 등 일반 블루투스 기기 연결에 함께 쓸 수 없습니다.
화면 미러링·클립보드 공유·파일 드래그 앤 드롭은 제공하지 않습니다.

**현재 알파 소스 공개 단계입니다.** 가상 BLE 및 Windows UI 검증과 별개로,
이 수정판의 실제 동글·iPad 연결과 절전 복귀·설치 프로그램 검증은 남아 있습니다.

[영문 설치 가이드](../README.md#run-from-source-on-windows) · [언어 지원](../LANGUAGES.md) · [실기 검증 상태](HARDWARE_VALIDATION.md)

## 실행

Windows 10/11, Python 3.10 이상을 준비하고 영문 가이드에 따라 의존성·필요한
펌웨어·동글 드라이버를 설치합니다.

```powershell
.\.venv\Scripts\pythonw.exe -m glideleaf --setup
.\.venv\Scripts\pythonw.exe -m glideleaf --tray
```

iPad의 **설정 → Bluetooth → Windows Pointer & Keyboard**에서 페어링하세요.
앱의 **포인터 · 키보드 설정 → 언어**에서 9개 언어 중 하나를 선택할 수 있습니다.
기본값은 시스템 언어 자동 선택입니다. UI 언어는 키보드 배열과 별개입니다.

기존 사용자 설정·페어링은 `%LOCALAPPDATA%\WinUC`에 유지됩니다.
삭제 전 동글 설정 화면에서 해당 동글을 일반 Bluetooth로 복원하세요.

## 동글이 검색되지 않을 때

문제가 발생하는 PC에서 **동글 설정 / 복원 → USB 진단 정보 복사**를 누르세요.
검색 실패와 실제 장치 없음은 구분해서 표시하며, 진단에는 USB 식별자·분류·드라이버 서비스가 포함됩니다.
장치 일련번호 뒤쪽과 페어링 키·입력 로그는 수집하지 않습니다.

Python 없이도 다음 명령으로 해당 PC의 진단 정보를 복사할 수 있습니다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/diagnose_usb.ps1 -Copy
```

또는 `python -m glideleaf --diagnose usb-diagnostics.json`으로 저장할 수 있습니다.
동글 모델명과 함께 검토한 진단 결과를 전달해 주세요. 이 작업은 드라이버를 변경하지 않습니다.

## fuba님께 감사드립니다

[WinUC](https://github.com/fuba/winuc)를 만들고 공개해 주신 fuba님께 감사드립니다.
그 작업 덕분에 Glideleaf를 시작할 수 있었습니다.
원본 Git 이력과 MIT 라이선스·Copyright (c) 2026 fuba를 보존했습니다.
이 저장소는 독립 수정판이며 Apple이나 fuba의 공식 제품이 아닙니다.
