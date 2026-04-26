# 商标与品牌使用

> [English](TRADEMARKS.md) · 简体中文

## License vs 商标

OmniTrade 源代码采用 [MIT](LICENSE) 协议 —— 你可以自由复制、fork、
修改、再分发，包括商业用途。**MIT 协议不授予商标权。**

## 受保护范围

下列内容是项目商标。即使你 fork 了 MIT 代码或基于它二次开发，请遵
守下面的规则：

- **「OmniTrade」名称**（作为项目 / 产品名）
- **指南针标识 logo**（`assets/logo.svg`、`assets/logo-horizontal.svg`、
  `assets/favicon.svg`、`assets/logo-mono.svg`）
- **OmniTrade 视觉调性**（特定的 Agno 紫 → 青渐变 + 珊瑚色高亮辐条
  的组合，当其用法可能暗示官方关联时）

## 无需许可的使用

- **引用与讨论**：博客、幻灯、talk、对比、评测、文档里直接说「我跑
  OmniTrade」「我 fork 了 OmniTrade 改了 X」「OmniTrade 比我之前的方
  案快」都没问题。
- **如实标注**：如果你的项目衍生自 OmniTrade，可以说「Based on
  OmniTrade」/「Derived from OmniTrade」，附 https://github.com/gong1414/omnitrade
  链接。
- **logo 合理使用**：教学材料、会议演讲、关于 OmniTrade 的文章里使
  用未经修改的 logo。**不要**改动、改色、扭曲 logo 暗示官方背书。

## 受限使用（请先开 issue 询问）

下面这些使用方式可能让一个理性观察者误以为你的项目 / 产品是官方
OmniTrade、或者得到了官方背书。请在做这些之前先开 issue 拿到书面
许可：

- **fork / 衍生项目命名为 「OmniTrade-X」** 之类容易和上游混淆的名
  字（比如 "OmniTrade Pro"、"OmniTrade Cloud"、"OmniTrade-as-a-Service"）
- **把 logo 当成主品牌元素** 用在以付费方式转售 OmniTrade 或其 fork
  的产品 / 服务 / SaaS 上
- **生产或售卖周边商品**（T 恤、贴纸、马克杯）印 OmniTrade 名称或
  logo
- **在域名里用 OmniTrade 名称** 让人误以为是官方站
  （`omnitrade-official.com`、`omnitrade.io` 这类）。能清晰区分的域
  名（`omnitrade-fork-myname.com`）通常没问题，但请在站内回链上游

## fork 的推荐做法

如果你 fork 后大幅改动 OmniTrade、面向不同受众，最干净的做法：

1. 给用户面向的产品起个新名字（比如 "MyAlphaBot"）
2. 保留源码协议（MIT）不变
3. 保留 README 的 `🙏 Acknowledgments` 段 —— 把 OmniTrade 站在哪些
   开源项目肩膀上的事实保留
4. 在你 README 顶部加一行 attribution：
   `Based on [OmniTrade](https://github.com/gong1414/omnitrade) (MIT).`
5. 替换 `assets/logo*.svg` 成你自己的品牌资产

这样你完全拥有 fork 的品牌，同时尊重 MIT 条款，并把上游贡献者的署
名留下。

## 报告混淆

如果你看到某个 fork、产品或域名以可能误导用户的方式使用 OmniTrade
名称或 logo —— 特别是任何暗示官方背书付费服务的做法，或者任何以
OmniTrade 名义吸纳用户资金的行为 —— 请开 issue 附上 URL。我们没有
律师团；我们只是希望用户不要被混淆。

## 有问题？

开 issue。我们宁可花一两句澄清，也不希望有人因为不确定边界而不敢用。

— *本文件不是法律建议。源代码以 [LICENSE](LICENSE) 中的 MIT 条款为
准；本商标声明是补充性质，反映社区惯例预期，不是可执行合同。*
