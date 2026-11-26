import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';

const _placeholderColor = Color(0x59B8AE9E);

/// 封面 URL 归一化（与详情页口径一致）：
/// - seed 静态值是相对路径（如 2025/12/xx.jpg）→ 拼 CDN 前缀；
/// - 观测封面是完整 https URL 或 // 协议相对 → 原样/补协议；
/// - 空值 → null（调用方回退本地占位封面）。
String? coverImageUrl(String? raw) {
  if (raw == null || raw.isEmpty) return null;
  if (raw.startsWith('http')) return raw;
  if (raw.startsWith('//')) return 'https:$raw';
  return 'https://rss.sfacg.com/web/novel/images/NovelCover/Big/$raw';
}

/// 占位底色板（柔和低饱和，白色首字符可读），按 nid hash 绑定——
/// 同一本书永远同色，相邻行自然错开（与作者榜头像同范式）。
const _palette = [
  Color(0xFF7C6F64), // 暖灰棕
  Color(0xFF6B7A8F), // 灰蓝
  Color(0xFF8A6F7C), // 灰紫
  Color(0xFF6F8F7C), // 灰绿
  Color(0xFF9A7B5F), // 驼
  Color(0xFF5F7D8C), // 青灰
];

String _firstChar(String s) =>
    s.isEmpty ? '' : String.fromCharCodes(s.runes.take(1));

/// 本地占位封面（用户裁定 2026-11-26）：原「官方 default 图远程兜底」
/// 退役——兜底图自己也是网络图，失败/加载中仍然白屏。现占位零网络
/// 依赖、任何时刻可渲染：nid 绑定的低饱和底色 + 半透明 app logo 水印
/// 铺底 + 中央书名首字符。
Widget placeholderCover(
  int nid,
  String? title, {
  double? width,
  double? height,
  BoxFit fit = BoxFit.cover,
  double radius = 0,
}) {
  final base = Container(
    width: width,
    height: height,
    color: _palette[nid.abs() % _palette.length],
    child: Stack(
      fit: StackFit.expand,
      children: [
        Opacity(
          opacity: .16,
          child: Image.asset(
            'assets/icon/app-icon-foreground.png',
            fit: fit,
          ),
        ),
        if (title != null && title.isNotEmpty)
          Center(
            child: Text(
              _firstChar(title),
              style: const TextStyle(
                fontSize: 22,
                fontWeight: FontWeight.w700,
                color: Colors.white,
              ),
            ),
          ),
      ],
    ),
  );
  return radius > 0
      ? ClipRRect(borderRadius: BorderRadius.circular(radius), child: base)
      : base;
}

/// 默认封面兜底（签名保留，title 传入时渲染首字符）。
Widget defaultCover(
  int nid, {
  String? title,
  BoxFit fit = BoxFit.cover,
  double radius = 0,
}) =>
    placeholderCover(nid, title, fit: fit, radius: radius);

/// 统一封面（磁盘 + 内存缓存，cached_network_image）：
/// - URL 走 coverImageUrl 归一化；空值直接本地占位；
/// - 加载中/失败两级兜底均为本地占位（不再回落远程默认图）。
Widget coverImage(
  String? raw,
  int nid, {
  String? title,
  double? width,
  double? height,
  BoxFit fit = BoxFit.cover,
  double radius = 0,
}) {
  final url = coverImageUrl(raw);
  if (url == null) {
    return placeholderCover(nid, title,
        width: width, height: height, fit: fit, radius: radius);
  }
  return CachedNetworkImage(
    imageUrl: url,
    width: width,
    height: height,
    fit: fit,
    placeholder: (_, _) =>
        placeholderCover(nid, title, fit: fit, radius: radius),
    errorWidget: (_, _, _) =>
        placeholderCover(nid, title, fit: fit, radius: radius),
  );
}

/// 缓存网络图（banner/大图等无 nid 兜底语义处）：失败显示占位色块
///（大图精选的"404 显示占位容器"口径不变）。
Widget cachedImage(
  String url, {
  double? width,
  double? height,
  BoxFit fit = BoxFit.cover,
}) {
  return CachedNetworkImage(
    imageUrl: url,
    width: width,
    height: height,
    fit: fit,
    placeholder: (_, _) => const ColoredBox(color: _placeholderColor),
    errorWidget: (_, _, _) => const ColoredBox(color: _placeholderColor),
  );
}
