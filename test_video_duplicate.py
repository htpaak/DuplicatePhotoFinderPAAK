import os
import sys
from video_processor import VideoProcessor
from video_duplicate_finder import VideoDuplicateFinder

def test_av_installation():
    """PyAV 라이브러리 로드 여부를 확인합니다"""
    print("PyAV 라이브러리 확인 중...")
    if VideoProcessor.check_av():
        print("✓ PyAV 라이브러리가 정상적으로 로드되었습니다.")
        return True
    else:
        print("✗ PyAV 라이브러리를 찾을 수 없습니다. 설치가 필요합니다.")
        print("  - 설치 방법: pip install av")
        return False

def test_video_processor(test_video_path):
    """VideoProcessor 기능을 테스트합니다"""
    print("\nVideoProcessor 테스트 중...")
    
    if not os.path.exists(test_video_path):
        print(f"✗ 테스트 비디오 파일이 존재하지 않습니다: {test_video_path}")
        return False
        
    processor = VideoProcessor()
    
    # 비디오 길이 확인
    duration = processor.get_video_duration(test_video_path)
    print(f"✓ 비디오 길이: {duration:.2f}초")
    
    # 프레임 추출 테스트
    positions = [10, 50, 90]  # 10%, 50%, 90% 위치
    print(f"✓ {', '.join([f'{p}%' for p in positions])} 위치에서 프레임 추출 중...")
    
    frames = processor.extract_multiple_frames(test_video_path, positions)
    if frames and len(frames) > 0:
        print(f"✓ {len(frames)}개 프레임 추출 완료")
        for i, frame in enumerate(frames):
            print(f"  - 프레임 {i+1}: 크기 {frame.shape}, 평균 밝기: {frame.mean():.1f}")
        return True
    else:
        print("✗ 프레임 추출 실패")
        return False

def test_duplicate_finder(test_folder_path):
    """VideoDuplicateFinder 기능을 테스트합니다"""
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
    
    return True

if __name__ == "__main__":
    # 명령줄 인수 처리
    if len(sys.argv) < 2:
        print("사용법: python test_video_duplicate.py <테스트_비디오_파일> [테스트_폴더_경로]")
        print("  - <테스트_비디오_파일>: 프레임 추출 테스트에 사용할 비디오 파일")
        print("  - [테스트_폴더_경로]: 중복 찾기 테스트에 사용할 폴더 (옵션)")
        sys.exit(1)
        
    test_video_path = sys.argv[1]
    test_folder_path = sys.argv[2] if len(sys.argv) > 2 else os.path.dirname(test_video_path)
    
    # PyAV 설치 확인
    if not test_av_installation():
        sys.exit(1)
        
    # VideoProcessor 테스트
    if not test_video_processor(test_video_path):
        sys.exit(1)
        
    # VideoDuplicateFinder 테스트
    test_duplicate_finder(test_folder_path)
    
    print("\n모든 테스트가 완료되었습니다!") 