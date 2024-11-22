import hashlib


def generate_md5(file_content: bytes):
    md5_hash = hashlib.md5()  # 创建 MD5 哈希对象
    md5_hash.update(file_content)  # 直接更新 MD5 哈希对象
    return md5_hash.hexdigest()
