#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
连接测试脚本 - 验证OSS和ClickHouse连通性
"""
import sys
import os

# 把项目根目录加入路径，这样能找到 .env 文件和 src 包
# 文件位置: src/test/connect.py → 上三层是项目根目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
# 从项目根目录加载 .env
load_dotenv(os.path.join(PROJECT_ROOT, '.env'))


def test_oss():
    """测试OSS连接"""
    print("=" * 60)
    print("【1/2】测试阿里云OSS连接...")
    print("=" * 60)
    print(f"Endpoint: {os.getenv('OSS_ENDPOINT')}")
    print(f"Bucket: {os.getenv('OSS_BUCKET_NAME')}")
    print(f"AccessKey ID: {os.getenv('OSS_ACCESS_KEY_ID')[:8]}...")
    print()

    try:
        from src.storage import OSSClient
        oss = OSSClient()

        print("✓ 客户端初始化成功")

        # 测试bucket访问并列出文件
        files = oss.list_files(max_keys=5)
        print(f"✓ Bucket访问成功，共找到 {len(files)} 个文件（最多显示5个）")
        for f in files[:5]:
            print(f"  - {f['key']} ({f['size']} bytes)")

        # 测试上传/下载/删除
        test_key = "_test_connection_tmp.txt"
        test_content = b"Hello OSS! Connection test"
        oss.upload_bytes(test_content, test_key)
        print(f"✓ 测试文件上传成功: {test_key}")

        downloaded = oss.download_bytes(test_key)
        assert downloaded == test_content, "下载内容与上传不一致"
        print("✓ 测试文件下载成功，内容校验通过")

        oss.delete_file(test_key)
        print("✓ 测试文件删除成功")

        print("\n✅ OSS连接测试全部通过！")
        return True

    except ImportError as e:
        print(f"\n❌ 导入失败: {e}")
        print("   请先安装依赖: pip install oss2 python-dotenv")
        return False
    except ValueError as e:
        print(f"\n❌ 配置错误: {e}")
        return False
    except Exception as e:
        print(f"\n❌ OSS连接失败: {type(e).__name__}: {e}")
        return False


def test_clickhouse():
    """测试ClickHouse连接"""
    print()
    print("=" * 60)
    print("【2/2】测试ClickHouse连接...")
    print("=" * 60)
    print(f"Host: {os.getenv('CK_HOST')}")
    print(f"Port: {os.getenv('CK_PORT')}")
    print(f"User: {os.getenv('CK_USER')}")
    print(f"Database: {os.getenv('CK_DATABASE')}")
    print()
    
    try:
        from src.storage import ClickHouseClient
        
        with ClickHouseClient() as ck:
            print("✓ 客户端初始化成功，连接已建立")
            
            ping_ok = ck.ping()
            print(f"✓ Ping测试: {'成功' if ping_ok else '失败'}")
            
            version = ck.query_value("SELECT version()")
            print(f"✓ ClickHouse版本: {version}")
            
            databases = ck.query_all("SHOW DATABASES")
            print(f"✓ 数据库列表（共{len(databases)}个）:")
            for db in databases:
                print(f"  - {db[0]}")
            
            tables = ck.get_tables()
            print(f"✓ 当前库 {ck.database} 中的表（共{len(tables)}个）:")
            for t in tables[:10]:
                print(f"  - {t}")
            if len(tables) > 10:
                print(f"  ... 还有 {len(tables)-10} 个表")
            
            result = ck.query_one("SELECT 1+1 AS test_val")
            assert result[0] == 2, "查询计算结果错误"
            print("✓ SQL查询测试通过: SELECT 1+1 =", result[0])
        
        print("\n✅ ClickHouse连接测试全部通过！")
        return True
    
    except ImportError as e:
        print(f"\n❌ 导入失败: {e}")
        print("   请先安装依赖: pip install clickhouse-connect python-dotenv")
        return False
    except ValueError as e:
        print(f"\n❌ 配置错误: {e}")
        return False
    except Exception as e:
        print(f"\n❌ ClickHouse连接失败: {type(e).__name__}: {e}")
        return False


def main():
    print("\n" + "🚀 开始连接测试".center(60, "="))
    print()

    results = {
        "OSS": test_oss(),
        "ClickHouse": test_clickhouse(),
    }

    print()
    print("=" * 60)
    print("📊 测试总结".center(60))
    print("=" * 60)
    for name, ok in results.items():
        status = "✅ 通过" if ok else "❌ 失败"
        print(f"  {name}: {status}")
    print()

    all_ok = all(results.values())
    if all_ok:
        print("🎉 所有连接测试通过！可以开始开发了。")
    else:
        print("⚠️  部分测试失败，请检查配置、网络或安全组设置。")
        sys.exit(1)


if __name__ == "__main__":
    main()