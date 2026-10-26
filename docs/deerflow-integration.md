# 接回 DeerFlow

本项目提供一个可选公共契约扩展，向 DeerFlow 暴露知识检索与工单查询。独立平台无需安装该契约。

## 1. 安装

在用于运行 DeerFlow 的 Python 环境中安装：

```powershell
python -m pip install -e G:/Agent/deer-flow-main/backend/packages/extension-api
python -m pip install -e G:/Agent/support-flow
```

也可用 DeerFlow 的扩展管理命令安装这个可信本地目录；源环境必须能解析到 0.2.9 公共契约。加载入口为 `supportflow.deerflow_extension:install`。

## 2. 绑定本人账号

先启动 SupportFlow，在本机使用 `POST /api/auth/login` 登录本人账号。将返回的访问令牌放入 **DeerFlow 进程环境变量**，不要放进提示词或 Git 配置文件。令牌有效期为 12 小时，需要到期后重新登录。

在 DeerFlow 的 `config.yaml` 中显式配置宿主用户到令牌环境变量的映射：

```yaml
plugins:
  - name: supportflow
    use: supportflow.deerflow_extension:install
    enabled: true
    config:
      enabled: true
      base_url: http://127.0.0.1:8010
      principal_token_env:
        "这里替换为真实的DeerFlow用户ID": SUPPORTFLOW_ALICE_TOKEN
```

配置属于部署操作，不允许模型或网页动态指定映射。重启 DeerFlow Gateway，并确认插件能力已启用。容器部署需把 `base_url` 换成容器可达的 SupportFlow 服务地址。

## 3. 可用工具与权限

- `supportflow_search(query)`：检索本部署共享知识。
- `supportflow_ticket(ticket_id)`：查询绑定的 SupportFlow 账号有权访问的工单。

当前用户没有显式映射时拒绝调用。工具使用宿主提供的 `principal.user_id`，不采纳模型传入的 user_id。最终工单资源权限由 SupportFlow 再次校验。

扩展不暴露工单确认或状态修改。用户仍需在 SupportFlow 界面完成有写入效果的业务步骤。

适配器已使用公共契约注册测试与模拟 HTTP 验证身份绑定；完整 DeerFlow Gateway 内的运行需在已配置该服务的环境中联调，不把离线测试当成宿主集成验收。
