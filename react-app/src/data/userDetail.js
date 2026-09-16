import { groupOwnerAnalytics } from "./ownerAnalytics";

export function buildUserDetail(modules = [], filterModules = []) {
  return {
    owners: groupOwnerAnalytics(modules, filterModules),
  };
}

export function selectOwners(owners = [], filterUsers = []) {
  if (!filterUsers.length) return owners;
  const selected = new Set(filterUsers);
  return owners.filter((owner) => selected.has(owner.ownerKey));
}
