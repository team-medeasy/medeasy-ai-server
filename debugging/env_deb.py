import os
from dotenv import load_dotenv

# 현재 작업 디렉토리 출력
print(f"디버그: 현재 작업 디렉토리 = {os.getcwd()}")

# .env 파일 내용 읽기
env_file = os.path.join(os.getcwd(), '.env')
if os.path.exists(env_file):
    print(f"디버그: .env 파일 존재함 = {env_file}")
    try:
        with open(env_file, 'r') as f:
            env_contents = f.read()
            print(f"디버그: .env 파일 내용 (비밀번호 가림):")
            for line in env_contents.strip().split('\n'):
                if line.strip() and not line.strip().startswith('#'):
                    if 'password' in line.lower() or 'secret' in line.lower():
                        key_part = line.split('=')[0] if '=' in line else line
                        print(f"  {key_part}=********")
                    else:
                        print(f"  {line}")
    except Exception as e:
        print(f"디버그: .env 파일 읽기 오류: {e}")
else:
    print(f"디버그: .env 파일이 존재하지 않음")

# 환경 변수 로드
print("디버그: 환경 변수 로드 중...")
load_dotenv()

# MongoDB URL 확인
mongo_url = os.getenv("MONGO_URL")
if mongo_url:
    print(f"디버그: MONGO_URL 환경 변수 원본 = {mongo_url}")
    # @ 기호 개수 확인
    at_count = mongo_url.count('@')
    print(f"디버그: MONGO_URL의 @ 기호 개수 = {at_count}")
    
    # URL 유효성 확인
    if at_count > 1:
        print(f"디버그: MONGO_URL에 @ 기호가 여러 개 있습니다. 이는 유효하지 않은 형식입니다.")
        parts = mongo_url.split('@')
        print(f"디버그: MONGO_URL 분리된 부분 = {parts}")
        
        # 수정 제안
        if len(parts) == 3:  # mongodb://user:pass@host@port 패턴
            protocol_auth = parts[0]
            host_port = '@'.join(parts[1:])
            if ':' in protocol_auth:
                protocol, auth = protocol_auth.split('://')
                print(f"디버그: 올바른 URL 형식은 {protocol}://{auth}@{host_port} 입니다.")

print("\n환경 변수 확인 완료")