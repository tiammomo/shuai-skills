# Official Docs Index

## Contents

- [Authentication And Token Docs](#authentication-and-token-docs)
- [Docx Document APIs](#docx-document-apis)
- [Drive And Media APIs](#drive-and-media-apis)
- [What These Links Cover](#what-these-links-cover)

## Authentication And Token Docs

- [How to choose which type of token to use](https://open.feishu.cn/document/uAjLw4CM/ugTN1YjL4UTN24CO1UjN/trouble-shooting/how-to-choose-which-type-of-token-to-use)
- [Get app_access_token for a self-built app](https://open.feishu.cn/document/ukTMukTMukTM/ukDNz4SO0MjL5QzM/auth-v3/auth/app_access_token_internal)
- [Get tenant_access_token for a self-built app](https://open.feishu.cn/document/ukTMukTMukTM/ukDNz4SO0MjL5QzM/auth-v3/auth/tenant_access_token_internal)
- [Obtain OAuth code](https://open.feishu.cn/document/authentication-management/access-token/obtain-oauth-code)
- [Get user_access_token](https://open.feishu.cn/document/authentication-management/access-token/get-user-access-token)

Legacy references still useful when debugging older flows:

- [OIDC v1 get user_access_token](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/authen-v1/oidc-access_token/create)
- [OIDC v1 refresh user_access_token](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/authen-v1/oidc-refresh_access_token/create)
- [v1 get user_access_token](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/authen-v1/access_token/create)
- [v1 refresh user_access_token](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/authen-v1/refresh_access_token/create)

## Docx Document APIs

- [Create document](https://open.feishu.cn/document/ukTMukTMukTM/uUDN04SN0QjL1QDN/document-docx/docx-v1/document/create)
- [Get document metadata](https://open.feishu.cn/document/ukTMukTMukTM/uUDN04SN0QjL1QDN/document-docx/docx-v1/document/get)
- [Get raw document content](https://open.feishu.cn/document/ukTMukTMukTM/uUDN04SN0QjL1QDN/document-docx/docx-v1/document/raw_content)
- [Convert Markdown or HTML into document blocks](https://open.feishu.cn/document/ukTMukTMukTM/uUDN04SN0QjL1QDN/document-docx/docx-v1/document/convert)
- [Create document blocks](https://open.feishu.cn/document/ukTMukTMukTM/uUDN04SN0QjL1QDN/document-docx/docx-v1/document-block-children/create)

## Drive And Media APIs

- [Create folder](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/drive-v1/file/create_folder)
- [Upload media](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/drive-v1/media/upload_all)

## What These Links Cover

Use the auth links when you need:

- app credentials
- tenant or user token acquisition
- token refresh behavior
- token type selection

Use the docx links when you need:

- create or read document content
- convert Markdown or HTML into blocks
- insert content into docx documents

Use the drive links when you need:

- create folders for sync targets
- upload images or attachments into a document workflow
