export type BusinessCategory = {
  id: string;
  name: string;
  slug: string;
  children: BusinessCategory[];
};
