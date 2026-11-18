import 'package:flutter/material.dart';

/// 官方默认封面兜底（用户拍板 2026-11-18）：cover_url 为空时用官方
/// default / defaultNew 两张图，按 nid 取余绑定，避免全部同图的单调感。
const _defaultCovers = [
  'https://rs.sfacg.com/web/novel/images/NovelCover/Big/default.jpg',
  'https://rs.sfacg.com/web/novel/images/NovelCover/Big/defaultNew.jpg',
];

String defaultCoverUrl(int nid) => _defaultCovers[nid.abs() % 2];

/// 默认封面兜底图。radius>0 时裁圆角（与封面卡一致的 10）。
Widget defaultCover(int nid, {BoxFit fit = BoxFit.cover, double radius = 0}) {
  final image = Image.network(defaultCoverUrl(nid), fit: fit);
  return radius > 0
      ? ClipRRect(borderRadius: BorderRadius.circular(radius), child: image)
      : image;
}
