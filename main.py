import sys
import os
import ctypes # 추가
import argparse # 인수 파싱을 위해 추가
# import winshell # 바로 가기 생성 안 하므로 제거
# import pythoncom # 바로 가기 생성 안 하므로 제거
# from win32com.client import Dispatch # 바로 가기 생성 안 하므로 제거

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

# 비디오 중복 찾기 테스트를 위한 임포트
from video_processor import VideoProcessor
from video_duplicate_finder import VideoDuplicateFinder

# --- 설정 변수 정의 (바로 가기 관련 변수 제거) ---
# APP_NAME = "DuplicatePhotoFinder" # MYAPPID 에서만 사용
COMPANY_NAME = "htpaak"
PRODUCT_NAME = "DuplicatePhotoFinderPAAK"
APP_VERSION = "1.0.0" 
MYAPPID = f"{COMPANY_NAME}.{PRODUCT_NAME}.{APP_VERSION}"

ICON_PATH = os.path.join(project_root, "assets", "icon.ico")
# SCRIPT_TO_RUN_PATH = os.path.abspath(__file__) # 바로 가기에서 사용되던 변수 제거
# PYTHON_EXE_PATH = sys.executable # 바로 가기에서 사용되던 변수 제거
# SHORTCUT_NAME = f"{APP_NAME}.lnk" # 바로 가기에서 사용되던 변수 제거
# try: # 바로 가기 경로 계산 로직 제거
#     DESKTOP_PATH = winshell.desktop() 
#     SHORTCUT_PATH = os.path.join(DESKTOP_PATH, SHORTCUT_NAME) 
# except Exception as e:
#     print(f"Error getting desktop path: {e}")
#     DESKTOP_PATH = None
#     SHORTCUT_PATH = None
# --- 설정 변수 정의 끝 ---

# 비디오 중복 찾기 테스트 함수 추가
def run_video_duplicate_test(test_video_path, test_folder_path=None):
    """비디오 중복 찾기 기능을 테스트합니다."""
    if test_folder_path is None:
        test_folder_path = os.path.dirname(test_video_path)
    
    print("\n===== 비디오 중복 찾기 테스트 시작 =====")
    
    # PyAV 라이브러리 확인
    print("\nPyAV 라이브러리 확인 중...")
    if not VideoProcessor.check_av():
        print("✗ PyAV 라이브러리를 찾을 수 없습니다. 설치가 필요합니다.")
        print("  - 설치 방법: pip install av")
        return False
    print("✓ PyAV 라이브러리가 정상적으로 로드되었습니다.")
    
    # 비디오 프로세서 테스트
    print("\nVideoProcessor 테스트 중...")
    if not os.path.exists(test_video_path):
        print(f"✗ 테스트 비디오 파일이 존재하지 않습니다: {test_video_path}")
        return False
    
    processor = VideoProcessor()
    
    # 성능 최적화 정보 출력
    try:
        import numba
        print(f"✓ Numba 최적화 사용 가능: 버전 {numba.__version__}")
        try:
            if numba.cuda.is_available():
                print(f"✓ CUDA 가속 사용 가능: 장치 {numba.cuda.get_current_device().name}")
            else:
                print("✗ CUDA 가속을 사용할 수 없습니다. CPU 기반 최적화만 사용됩니다.")
        except Exception:
            print("✗ CUDA 확인 중 오류가 발생했습니다. CPU 기반 최적화만 사용됩니다.")
    except ImportError:
        print("✗ Numba 최적화를 사용할 수 없습니다. 기본 NumPy만 사용됩니다.")
    
    # 하드링크 검사 기능 확인
    print("\n기능 활성화 상태:")
    print("✓ 하드링크 검사: 활성화됨")
    print("✓ 수평 반전 이미지 검사: 활성화됨")
    if hasattr(processor, 'use_hw_acceleration') and processor.use_hw_acceleration:
        print("✓ 하드웨어 가속: 활성화됨")
    else:
        print("✗ 하드웨어 가속: 비활성화됨")
    
    # 비디오 길이 확인
    duration = processor.get_video_duration(test_video_path)
    print(f"✓ 비디오 길이: {duration:.2f}초")
    
    # 프레임 추출 테스트
    positions = [10, 50, 90]  # 10%, 50%, 90% 위치
    print(f"✓ {', '.join([f'{p}%' for p in positions])} 위치에서 프레임 추출 중...")
    
    frames = processor.extract_multiple_frames(test_video_path, positions)
    if not frames or len(frames) == 0:
        print("✗ 프레임 추출 실패")
        return False
    
    print(f"✓ {len(frames)}개 프레임 추출 완료")
    for i, frame in enumerate(frames):
        print(f"  - 프레임 {i+1}: 크기 {frame.shape}, 평균 밝기: {frame.mean():.1f}")
    
    # VideoDuplicateFinder 테스트
    print("\nVideoDuplicateFinder 테스트 중...")
    if not os.path.exists(test_folder_path) or not os.path.isdir(test_folder_path):
        print(f"✗ 테스트 폴더가 존재하지 않습니다: {test_folder_path}")
        return False
    
    finder = VideoDuplicateFinder()
    
    # 폴더 내 모든 비디오 파일 찾기
    video_files = []
    for root, _, files in os.walk(test_folder_path):
        for file in files:
            file_path = os.path.join(root, file)
            if finder.is_video_file(file_path):
                video_files.append(file_path)
    
    if not video_files:
        print(f"✗ 폴더 내에 비디오 파일이 없습니다: {test_folder_path}")
        return False
    
    print(f"✓ {len(video_files)}개 비디오 파일 발견")
    
    # 중복 찾기 실행
    print("✓ 중복 비디오 검색 중...")
    duplicates = finder.find_duplicates(video_files)
    
    # 결과 출력
    if duplicates:
        print(f"✓ {len(duplicates)}개 중복 그룹 발견:")
        for i, (original, dupes) in enumerate(duplicates):
            print(f"\n그룹 {i+1}:")
            print(f"  원본: {os.path.basename(original)}")
            print("  중복:")
            for dupe, similarity in dupes:
                print(f"    - {os.path.basename(dupe)} (유사도: {similarity:.1f}%)")
    else:
        print("✓ 중복 비디오가 발견되지 않았습니다.")
    
    print("\n===== 비디오 중복 찾기 테스트 완료 =====")
    return True

# 명령줄 인수 파싱 함수 추가
def parse_arguments():
    """명령줄 인수를 파싱합니다."""
    parser = argparse.ArgumentParser(description="DuplicatePhotoFinderPAAK - 이미지 및 비디오 중복 찾기 프로그램")
    parser.add_argument("--test-video", type=str, help="비디오 중복 찾기 테스트에 사용할 비디오 파일")
    parser.add_argument("--test-folder", type=str, help="비디오 중복 찾기 테스트에 사용할 폴더 (선택 사항)")
    return parser.parse_args()

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

# --- 바로 가기 생성 로직 제거됨 ---
# if SHORTCUT_PATH and os.path.exists(project_root): 
#    ...
# --- 바로 가기 생성 끝 ---

# 애플리케이션의 메인 로직
if __name__ == '__main__':
    # 명령줄 인수 파싱
    args = parse_arguments()
    
    # 비디오 중복 찾기 테스트 모드 확인
    if args.test_video:
        run_video_duplicate_test(args.test_video, args.test_folder)
        sys.exit(0)
    
    # 일반 모드 - GUI 시작
    app = QApplication(sys.argv)
    
    # --- 애플리케이션 아이콘 설정 ---
    if os.path.exists(ICON_PATH):
        app.setWindowIcon(QIcon(ICON_PATH))
    # --- 아이콘 설정 끝 ---
    
    app.setStyle('Fusion') # Fusion 스타일 적용
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
