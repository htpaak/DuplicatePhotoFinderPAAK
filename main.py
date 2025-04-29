import sys
import os
import ctypes # 추가
import winshell # 추가
import pythoncom # 추가 (pywin32 필요)
from win32com.client import Dispatch # 추가 (pywin32 필요)

# 프로젝트 루트 경로 계산 (main.py 기준)
project_root = os.path.dirname(os.path.abspath(__file__))
# sys.path 에 추가 (이미 되어 있다면 중복 방지) - ui/main_window.py 에서도 하므로 여기서는 불필요할 수 있음
# if project_root not in sys.path:
#     sys.path.insert(0, project_root)

from log_setup import setup_logging
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QIcon # QIcon 임포트 추가
from PyQt5.QtCore import Qt
from ui.main_window import MainWindow

# --- 설정 변수 정의 (ui/main_window.py 에서 이동) ---
APP_NAME = "DuplicatePhotoFinder"
COMPANY_NAME = "MyCompanyName"
PRODUCT_NAME = "DuplicatePhotoFinder"
APP_VERSION = "1.0.0" 
MYAPPID = f"{COMPANY_NAME}.{PRODUCT_NAME}.{APP_VERSION}"

ICON_PATH = os.path.join(project_root, "assets", "icon.ico")
# SCRIPT_PATH 는 바로 가기 생성 시 사용될 실제 실행 대상 스크립트 경로
# 여기서는 main.py 를 실행할 것이므로 main.py 경로 또는 ui/main_window.py 경로 지정 필요
# 만약 바로 가기가 ui/main_window.py 를 직접 실행하게 하려면 해당 경로 사용
# SCRIPT_TO_RUN_PATH = os.path.join(project_root, "ui", "main_window.py") 
# 여기서는 main.py 를 실행하도록 설정 (권장)
SCRIPT_TO_RUN_PATH = os.path.abspath(__file__) 

PYTHON_EXE_PATH = sys.executable 
SHORTCUT_NAME = f"{APP_NAME}.lnk" 
try:
    DESKTOP_PATH = winshell.desktop() 
    SHORTCUT_PATH = os.path.join(DESKTOP_PATH, SHORTCUT_NAME) 
except Exception as e:
    print(f"Error getting desktop path: {e}")
    DESKTOP_PATH = None
    SHORTCUT_PATH = None
# --- 설정 변수 정의 끝 ---


# DPI 스케일링 활성화 (QApplication 생성 전 호출)
QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)

# --- Windows 작업 표시줄 아이콘 설정 (AppUserModelID) ---
try:
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(MYAPPID)
    print(f"Set AppUserModelID using ctypes: {MYAPPID}")
except ImportError:
    print("Warning: 'ctypes' module not found. Taskbar icon might not be set correctly on Windows.")
except AttributeError:
    # Windows가 아니거나 필요한 API가 없을 경우
    pass
except Exception as e:
    print(f"Error setting AppUserModelID using ctypes: {e}")
# --- AppUserModelID 설정 끝 ---

setup_logging() # 항상 호출 (내부에서 조건 확인)

# --- 바로 가기 생성 또는 업데이트 ---
if SHORTCUT_PATH and os.path.exists(project_root): # 작업 디렉토리 project_root 사용
    try:
        target_exe = PYTHON_EXE_PATH # 항상 python.exe 사용

        icon_exists = os.path.exists(ICON_PATH)

        with winshell.shortcut(SHORTCUT_PATH) as shortcut:
            shortcut.path = target_exe
            # 바로 가기가 실행할 스크립트는 main.py
            shortcut.arguments = f'"{SCRIPT_TO_RUN_PATH}"' 
            shortcut.working_directory = project_root # 작업 디렉토리: 프로젝트 루트
            shortcut.description = f"{PRODUCT_NAME} Application"

            if icon_exists:
                shortcut.icon_location = (ICON_PATH, 0)
            else:
                print(f"Warning: Shortcut icon not found at {ICON_PATH}")
        
        print(f"Shortcut created/updated: {SHORTCUT_PATH}")

    except Exception as e:
        print(f"Error creating or updating shortcut: {e}")
elif not SHORTCUT_PATH:
     print("Could not determine shortcut path. Skipping shortcut creation.")
# --- 바로 가기 생성 끝 ---


# 애플리케이션의 메인 로직
if __name__ == '__main__':
    app = QApplication(sys.argv)
    
    # --- 애플리케이션 아이콘 설정 ---
    if os.path.exists(ICON_PATH):
        app.setWindowIcon(QIcon(ICON_PATH))
    # --- 아이콘 설정 끝 ---
    
    app.setStyle('Fusion') # Fusion 스타일 적용
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
