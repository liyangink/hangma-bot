# 观战器素材

本目录保存观战页使用的外部素材。全部为本地文件，页面通过同源路径 `/assets/…` 读取
（Content-Security-Policy 只允许 `'self'` 与 `data:`，不引用任何外部 CDN）。

## tiles/：麻将牌面

- 来源：[FluffyStuff/riichi-mahjong-tiles](https://github.com/FluffyStuff/riichi-mahjong-tiles)
  （Regular 变体的 SVG 原文件）。
- 许可证：**CC0 1.0 公有领域**（见该仓库 LICENSE.md），可自由使用与再分发。
- 覆盖范围：万 1—9（`Man1`—`Man9`）、筒 1—9（`Pin1`—`Pin9`）、条 1—9
  （`Sou1`—`Sou9`）、字牌 `Ton` 东 / `Nan` 南 / `Shaa` 西 / `Pei` 北 /
  `Chun` 中 / `Hatsu` 发 / `Haku` 白，外加 `Back` 牌背、`Front` 空白牌面与
  `Blank` 备用。
- 单张为 300×400 的整牌矢量（含牌身），牌码到文件的映射见 `spectator/static/app.js`
  的 `TILE_ASSET_SUITS` 与 `TILE_ASSET_HONORS`。
- 财神在当前规则下是「白」（`Haku`）；页面在牌面右上角叠加金色「财」标记，不改动素材本体。

## table/felt.svg：牌桌毛毡纹理

本项目自行绘制的轻量图案（斜纹 + 少量噪点），叠加在牌桌的绿色渐变之上，模拟毛毡质感。

## avatars/：座位头像

本项目自行绘制的扁平头像（`seat-me`/`seat-right`/`seat-top`/`seat-left`）。
官方快照不提供对手身份与头像，这里只作为座位标识，不代表任何真实玩家形象。

## 维护约定

- 新增素材必须同时说明来源、许可证与用途；不得引入需要在线加载的资源。
- 只放图片/字体等静态资源；服务端按扩展名白名单提供文件，并拒绝路径穿越。
