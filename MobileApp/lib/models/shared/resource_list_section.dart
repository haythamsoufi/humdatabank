import 'resource.dart';
import 'resource_subcategory.dart';

/// One heading + grid of resources (from grouped API response).
class ResourceListSection {
  final ResourceSubcategory? subcategory;
  final List<Resource> resources;

  const ResourceListSection({
    required this.subcategory,
    required this.resources,
  });
}
