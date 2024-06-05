import networkx as nx
import itertools

# Get a list of 60 hamiltonian paths used in the 3d version of the ordered J1
# triangulation, and dump it to stdout.
if __name__ == '__main__':
    # Graph of a double cube
    sign_vecs = list(itertools.product((-1, 1), repeat=3))
    permutations = itertools.permutations(range(1, 4))
    simplices = list(itertools.product(sign_vecs, permutations))

    G = nx.Graph()
    G.add_nodes_from(simplices)
    for s in sign_vecs:
        # interior connectivity of cubes
        G.add_edges_from(
            [
                ((s, (1, 2, 3)), (s, (1, 3, 2))),
                ((s, (1, 3, 2)), (s, (3, 1, 2))),
                ((s, (3, 1, 2)), (s, (3, 2, 1))),
                ((s, (3, 2, 1)), (s, (2, 3, 1))),
                ((s, (2, 3, 1)), (s, (2, 1, 3))),
                ((s, (2, 1, 3)), (s, (1, 2, 3))),
            ]
        )
    # connectivity between cubes in double cube
    for simplex in simplices:
        neighbor_sign = list(simplex[0])
        neighbor_sign[simplex[1][2] - 1] *= -1
        neighbor_simplex = (tuple(neighbor_sign), simplex[1])
        G.add_edge(simplex, neighbor_simplex)

    # Each of these simplices has an outward face in the specified direction; also,
    # the +x simplex of one cube is adjacent to the -x simplex of a cube adjacent in
    # the x direction, and similarly for the others.
    border_simplices = {
        # simplices in low-coordinate cube
        # -x
        ((-1, 0, 0), 1): ((-1, -1, -1), (1, 2, 3)),
        ((-1, 0, 0), 2): ((-1, -1, -1), (1, 3, 2)),
        # -y
        ((0, -1, 0), 1): ((-1, -1, -1), (2, 1, 3)),
        ((0, -1, 0), 2): ((-1, -1, -1), (2, 3, 1)),
        # -z
        ((0, 0, -1), 1): ((-1, -1, -1), (3, 1, 2)),
        ((0, 0, -1), 2): ((-1, -1, -1), (3, 2, 1)),
        # simplices in one-high-coordinate cubes
        # +x
        ((1, 0, 0), 1): ((1, -1, -1), (1, 2, 3)),
        ((1, 0, 0), 2): ((1, -1, -1), (1, 3, 2)),
        # +y
        ((0, 1, 0), 1): ((-1, 1, -1), (2, 1, 3)),
        ((0, 1, 0), 2): ((-1, 1, -1), (2, 3, 1)),
        # +z
        ((0, 0, 1), 1): ((-1, -1, 1), (3, 1, 2)),
        ((0, 0, 1), 2): ((-1, -1, 1), (3, 2, 1)),
    }

    # Need: Hamiltonian paths from each input to some output in each direction
    all_needed_hamiltonians = {}
    for i, s1 in border_simplices.items():
        for j, s2 in border_simplices.items():
            # I could cut the number of these in half or less via symmetry but I don't care
            if i[0] != j[0]:
                if (i, (j[0], 1)) in all_needed_hamiltonians.keys() or (
                    i,
                    (j[0], 2),
                ) in all_needed_hamiltonians.keys():
                    print(
                        f"skipping search for path from {i} to {j} because we have a path from {i} to {(j[0], 1) if (i, (j[0], 1)) in all_needed_hamiltonians.keys() else (j[0], 2)}"
                    )
                    continue
                print(f"searching for path from {i} to {j}")
                for path in nx.all_simple_paths(G, s1, s2):
                    if len(path) == 48:
                        # it's hamiltonian!
                        print(f"found hamiltonian path from {i} to {j}")
                        all_needed_hamiltonians[(i, j)] = path
                        break
                print(f"done looking for paths from {i} to {j}")
    print()
    print(all_needed_hamiltonians)
