import { create } from "zustand";
import { persist } from "zustand/middleware";

interface LocationState {
  selectedLocationId: string | null;
  setLocation: (id: string | null) => void;
}

export const useLocationStore = create<LocationState>()(
  persist(
    (set) => ({
      selectedLocationId: null,
      setLocation: (id) => set({ selectedLocationId: id }),
    }),
    { name: "tahinis-location" }
  )
);
