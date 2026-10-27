"""Buildings nearby (backend/agents/campus.py): search them, route into one, open it."""







class NearbyTools:
    def tool_search_nearby_buildings(self, query: str) -> dict:
        if self.campus is None:
            return {"error": "This building has no known neighbours."}
        result = self.campus.search(query)
        if self.emitting and result["buildings"]:
            self.events.append({"type": "elsewhere", "query": query, "buildings": [
                {"building": item["building_id"], "name": item["name"], "distance_m": item["distance_m"],
                 "total": item["total"], "first": item["results"][0]["name"] if item["results"] else None}
                for item in result["buildings"]]})
        return result

    def tool_route_to_building(self, start: str, building: str, destination: str) -> dict:
        if self.campus is None:
            return {"error": "This building has no known neighbours."}
        return self.campus.route(self, start, building, destination)

    def tool_open_nearby_building(self, building: str) -> dict:
        """Open a nearby building in the app (frontend/src/building/BuildingScreen.tsx `open_building`). When the
        route on the map leads there (route_to_building), the app continues it: the user stands at its entrance and
        the rest of the route is drawn. This session's building is not changed; the Guide there starts afresh."""
        if self.campus is None:
            return {"error": "This building has no known neighbours."}
        target = self.campus.resolve_building(building)
        name = self.campus.catalogue[target].get("name") or target
        if self.emitting:
            self.events.append({"type": "open_building", "building": target, "name": name})
        return {"opened": True, "building": name,
                "note": "The app now opens it; a route there on the map continues inside it. Say so in one line."}
