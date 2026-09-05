export type NamedReference = {
  id: string;
  name: string;
};

export type SearchArea = NamedReference & {
  country: NamedReference & { code: string; name_ru: string };
  province: (NamedReference & { code: string; name_ru: string }) | null;
  district: (NamedReference & { slug: string; name_ru: string }) | null;
  neighborhood: (NamedReference & { slug: string; name_ru: string }) | null;
  geometry: {
    type: 'MultiPolygon';
    coordinates: unknown[];
  };
  bbox: [number, number, number, number];
};
