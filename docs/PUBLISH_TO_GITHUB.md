> 资源版补充：优先将不含文献正文的 github-source ZIP 解压到新目录再提交；完整本地包保留句子供复跑。大型参考附件与获准公开的句子附件可分别挂 Releases，来源和权利见 DATA_LICENSE.md，勿将全部本地数据直接强制加入 Git。

# 发布到自己的独立仓库

建议名称RiceMind-engineering。描述：Independent engineering adaptation of RiceMind with documented differences, configurable workflows and audit records.

目标账号为 hsnakmnh，拟建仓库 RiceMind-engineering。整理者已确认作者允许公开单独提供的脚本及适配代码，见 ATTRIBUTION。远程创建与推送状态以实际执行记录为准。

## GitHub网页

New repository，填写名称与描述，公开目标选Public。不勾选自动README/.gitignore/LICENSE，因为本地已提供。创建空仓库后保存自己的地址，不填写作者仓库。

## Windows PowerShell 5.1

~~~powershell
Set-Location -LiteralPath 'D:\2026年9月\RindMind\github-release\RiceMind-engineering'
git init -b main
git add .
git status --short
git diff --cached --stat
git diff --cached --check
git config user.name '你的GitHub显示名'
git config user.email '你的提交邮箱或noreply邮箱'
git commit -m 'Prepare RiceMind engineering adaptation with provenance and usage docs'
git remote add origin https://github.com/hsnakmnh/RiceMind-engineering.git
git remote -v
git push -u origin main
~~~

身份仅设当前仓库，使用自己的身份。已有.git先看status/remote，不必重复init；origin已存在不重复add。认证不要把令牌写入URL或脚本。

Linux上传候选ZIP至新目录、解压进入后执行相同git子命令，不对包含运行数据的旧目录直接git add .。

发布后核对文档和Actions，以真实提交作为适配起点，确认后再标自己的版本。基线提交号不明，不宣称继承完整历史，也不盲目合并不相关历史。大结果另存发布并记录哈希/来源/条款。

官方步骤：https://docs.github.com/en/repositories/creating-and-managing-repositories/creating-a-new-repository

Git本地导入说明：https://docs.github.com/en/migrations/importing-source-code/using-the-command-line-to-import-source-code/adding-locally-hosted-code-to-github

CI使用核对时官方示例中的checkout/setup-python v7，GitHub托管runner；来源：https://github.com/actions/checkout ，https://github.com/actions/setup-python 。没有测试远端CI成功。
