import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_svg/flutter_svg.dart';

/// Whether [url] points at an SVG file (ignores query string and fragment).
bool isSvgLogoUrl(String url) {
  final uri = Uri.tryParse(url);
  final path = (uri?.path ?? url.split('?').first).toLowerCase();
  return path.endsWith('.svg');
}

/// Remote logo that renders both raster images and SVG files.
///
/// Backoffice sector logos can be uploaded as SVG, which [CachedNetworkImage]
/// cannot decode, so SVG URLs are drawn with [SvgPicture.network].
class NetworkLogoImage extends StatelessWidget {
  const NetworkLogoImage({
    super.key,
    required this.url,
    required this.size,
    required this.fallback,
  });

  final String url;
  final double size;
  final Widget fallback;

  @override
  Widget build(BuildContext context) {
    if (isSvgLogoUrl(url)) {
      return SvgPicture.network(
        url,
        width: size,
        height: size,
        fit: BoxFit.contain,
        placeholderBuilder: (_) => SizedBox(width: size, height: size),
        errorBuilder: (_, _, _) => fallback,
      );
    }
    final cachePx = (size * 2).round();
    return CachedNetworkImage(
      imageUrl: url,
      width: size,
      height: size,
      fit: BoxFit.contain,
      memCacheWidth: cachePx,
      memCacheHeight: cachePx,
      errorWidget: (_, _, _) => fallback,
    );
  }
}
