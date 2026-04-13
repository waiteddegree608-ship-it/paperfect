import os
import subprocess
import sys

def run_cmd(cmd, ignore_error=False):
    print(f"▶ 执行指令: {cmd}")
    try:
        subprocess.run(cmd, shell=True, check=True)
    except subprocess.CalledProcessError as e:
        if not ignore_error:
            print(f"❌ 指令执行失败: {e}")
            sys.exit(1)
        else:
            print(f"⚠️ 警告 (已忽略): {e}")

def main():
    repo_url = "https://github.com/waiteddegree608-ship-it/paperfect.git"
    
    print("="*40)
    print(" 🚀 开始上传项目到 GitHub")
    print("="*40)
    
    # Navigate to the project root directory before committing
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(project_root)
    
    # 1. 初始化
    if not os.path.exists(".git"):
        print("\n=> 初始化 Git 仓库...")
        run_cmd("git init")
        # 很多现代环境默认主分支是 main，防止兼容问题手动切换一下
        run_cmd("git checkout -b main", ignore_error=True)
    else:
        print("\n=> Git 仓库已存在。")
        run_cmd("git branch -M main", ignore_error=True)

    # 2. 检查未暂存文件
    print("\n=> 添加追踪更改的代码...")
    run_cmd("git add .")

    # 判断是否有更改需要提交
    status = subprocess.run("git status --porcelain", shell=True, capture_output=True, text=True).stdout
    if not status.strip():
        print("\n=> 当前没有需要提交的更改！代码区已经是最新的。")
    else:
        # 3. 提交代码
        msg = input("\n📝 请输入提交说明 (直接回车默认使用 'Initial commit / Auto Update') : ")
        if not msg.strip():
            msg = "Initial commit / Auto Update"
            
        print(f"\n=> 正在提交...")
        run_cmd(f'git commit -m "{msg}"')

    # 4. 配置远程仓库链接
    print("\n=> 配置远端服务器 (origin)...")
    try:
        remote_output = subprocess.check_output("git remote -v", shell=True, text=True)
        if "origin" not in remote_output:
            run_cmd(f"git remote add origin {repo_url}")
        else:
            # 已存在则强制修正一次 url，以防之前配错
            run_cmd(f"git remote set-url origin {repo_url}")
    except Exception:
        run_cmd(f"git remote add origin {repo_url}", ignore_error=True)

    # 5. 推送
    print(f"\n=> 正在推送到服务器: {repo_url}")
    print("⏳ 这可能需要花费一点时间，取决于网络速度...")
    
    try:
        run_cmd("git push -u origin main")
        print("\n" + "="*40)
        print(" 🎉 成功上传代码至 GitHub!")
        print(f" 👉 访问链接: {repo_url.replace('.git', '')}")
        print("="*40)
    except SystemExit:
        print("\n❌ 代码推送失败！")
        print("可能的原因：")
        print("1. 你可能还没有在命令行登录 GitHub（需先执行过 git config 配置）。")
        print("2. 网路连接 GitHub 失败，建议开启全局代理或者配置 git proxy。")
        print("3. 当前仓库中存在远端更新但本地未同步的情况（可以尝试 git pull 后再次运行）。")

if __name__ == "__main__":
    main()
