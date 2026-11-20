import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';

const _placeholderColor = Color(0x59B8AE9E);

/// 官方默认封面兜底（用户拍板 2026-11-18）：cover_url 为空时用官方
/// default / defaultNew 两张图，按 nid 取余绑定，避免全部同图的单调感。
const _defaultCovers = [
  'https://rs.sfacg.com/web/novel/images/NovelCover/Big/default.jpg',
  'https://rs.sfacg.com/web/novel/images/NovelCover/Big/defaultNew.jpg',
];

String defaultCoverUrl(int nid) => _defaultCovers[nid.abs() % 2];

/// 封面加载占位：加载中显示底色块而不是空槽；加载完成原样渲染。
Widget coverLoadingBuilder(BuildContext context, Widget child, ImageChunkEvent? progress) =>
    progress == null
        ? child
        : ColoredBox(color: const Color(0x59B8AE9E), child: child);

/// 封面 URL 归一化（与详情页口径一致）：
/// - seed 静态值是相对路径（如 2025/12/xx.jpg）→ 拼 CDN 前缀；
/// - 观测封面是完整 https URL 或 // 协议相对 → 原样/补协议；
/// - 空值 → null（调用方回退默认封面）。
String? coverImageUrl(String? raw) {
  if (raw == null || raw.isEmpty) return null;
  if (raw.startsWith('http')) return raw;
  if (raw.startsWith('//')) return 'https:$raw';
  return 'https://rss.sfacg.com/web/novel/images/NovelCover/Big/$raw';
}

/// 默认封面兜底图。radius>0 时裁圆角（与封面卡一致的 10）。
Widget defaultCover(int nid, {BoxFit fit = BoxFit.cover, double radius = 0}) {
  final image = CachedNetworkImage(
    imageUrl: defaultCoverUrl(nid),
    fit: fit,
    placeholder: (_, _) => const ColoredBox(color: _placeholderColor),
    errorWidget: (_, _, _) => const ColoredBox(color: _placeholderColor),
  );
  return radius > 0
      ? ClipRRect(borderRadius: BorderRadius.circular(radius), child: image)
      : image;
}

/// 统一的网络封面图（磁盘 + 内存缓存，cached_network_image）：
/// - URL 走 coverImageUrl 归一化；空值直接用官方默认封面；
/// - 加载中显示底色块（与 coverLoadingBuilder 同款）；
/// - 失败两级兜底：默认封面（自身再失败 → 色块）。
Widget coverImage(
  String? raw,
  int nid, {
  double? width,
  double? height,
  BoxFit fit = BoxFit.cover,
}) {
  final url = coverImageUrl(raw) ?? defaultCoverUrl(nid);
  return CachedNetworkImage(
    imageUrl: url,
    width: width,
    height: height,
    fit: fit,
    placeholder: (_, _) => const ColoredBox(color: _placeholderColor),
    errorWidget: (_, _, _) => Image(
      image: CachedNetworkImageProvider(defaultCoverUrl(nid)),
      width: width,
      height: height,
      fit: fit,
      errorBuilder: (_, _, _) =>
          const ColoredBox(color: _placeholderColor),
    ),
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
