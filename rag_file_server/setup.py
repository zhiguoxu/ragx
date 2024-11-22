from setuptools import setup, find_packages

setup(
    name='rag_file_mgr',
    version='0.1.1',
    packages=find_packages(where='src'),  # 指定包的位置
    package_dir={'': 'src'},
    package_data={"rag_file_server.config": ["*.json"]},
    install_requires=[],
    author='zhiguo',
    author_email='zhiguoxu2004@163.com',
    description='sdk of a file server',
    long_description="",
    long_description_content_type='text/markdown',
    url='https://github.com/xxx',
    classifiers=[]
)
