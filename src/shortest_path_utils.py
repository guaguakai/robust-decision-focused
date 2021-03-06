import torch
import torch.nn as nn
import torch.utils.data as data_utils
import torch.nn.functional as F
from torch.utils.data.sampler import SubsetRandomSampler

import networkx as nx
import numpy as np
from qpthlocal.qp import QPFunction
from qpthlocal.qp import QPSolvers
import random
import pickle

from linear import make_shortest_path_matrix

# Random Seed Initialization
SEED = random.randint(0,10000)
print("Random seed: {}".format(SEED))
torch.manual_seed(SEED)
np.random.seed(SEED)
random.seed(SEED)

def make_fc(num_features, num_targets, num_layers = 1, intermediate_size = 2048, activation = 'relu'):
    if num_layers > 1:
        if activation == 'relu':
            activation_fn = nn.ReLU
        elif activation == 'sigmoid':
            activation_fn = nn.Sigmoid
        else:
            raise Exception('Invalid activation function: ' + str(activation))
        net_layers = [nn.Linear(num_features, intermediate_size), activation_fn()]
        for hidden in range(num_layers-2):
            net_layers.append(nn.Linear(intermediate_size, intermediate_size))
            net_layers.append(activation_fn())
        net_layers.append(nn.Linear(intermediate_size, num_targets))
        net_layers.append(nn.Sigmoid())
        # net_layers.append(nn.ReLU())
        return nn.Sequential(*net_layers)
    else:
        return nn.Sequential(nn.Linear(num_features, num_targets), nn.Sigmoid())

class MeanNet(nn.Module):
    def __init__(self, n_features, n_targets, intermediate_size = 128):
        super(MeanNet, self).__init__()
        self.num_features = n_features # TODO
        self.num_targets = n_targets
        self.intermediate_size = intermediate_size

        self.fc1 = nn.Linear(self.num_features, intermediate_size)
        self.fc2 = nn.Linear(intermediate_size, self.num_targets)
        self.dropout = nn.Dropout(0.5)
        # self.fc3 = nn.Linear(intermediate_size, self.num_targets)

    def forward(self, x):
        x = nn.functional.relu(self.fc1(x))
        # x = self.dropout(x)
        x = self.fc2(x)
        # x = self.dropout(x)
        
        x = nn.Sigmoid()(x) * 5
        # x = nn.Softplus()(x)
        return x

        # x = nn.Dropout(x)
        # x = self.fc3(x)
        # return nn.Sigmoid()(x)

class VarianceNet(nn.Module):
    def __init__(self, n_features, n_targets, intermediate_size = 512):
        super(VarianceNet, self).__init__()
        self.num_features = n_features # TODO
        self.num_targets = n_targets
        self.intermediate_size = intermediate_size

        self.fc1 = nn.Linear(self.num_features, intermediate_size)
        self.fc2 = nn.Linear(intermediate_size, self.num_targets)
        self.dropout = nn.Dropout(0.5)
        # self.fc3 = nn.Linear(intermediate_size, self.num_targets)

    def forward(self, x):
        x = nn.functional.relu(self.fc1(x))
        # x = self.dropout(x)
        x = self.fc2(x)
        # x = self.dropout(x)
        x = nn.Sigmoid()(x) * 5
        # return nn.Sigmoid()(x)
        # x = nn.Softplus()(x)
        # x = x / torch.sum(x)
        return x


def generate_graph_geometric(n_nodes=100, p=0.2, n_instances=300, seed=SEED):
    generation_succeed = False
    print("Generating graph...")

    while not generation_succeed:
        original_graph = nx.random_geometric_graph(n_nodes, p)
        g = nx.DiGraph(original_graph)
        c = np.zeros(g.number_of_edges())
        for idx, (u,v) in enumerate(g.edges()):
            g[u][v]['idx'] = idx
            g[u][v]['weight'] = c[idx]
        
        if nx.is_connected(original_graph):
            generation_succeed = True
        else:
            generation_succeed = False

    print("Generating sources and destinations...")
    source_list = []
    dest_list = []
    for i in range(n_instances):
        source, dest = np.random.choice(list(g.nodes()), size=2, replace=False)
        source_list.append(source)
        dest_list.append(dest)

    print("Finish generating graph!")
    return g, c, source_list, dest_list

def generate_graph_erdos(n_nodes=100, p=0.2, n_instances=300, seed=SEED):
    generation_succeed = False
    print("Generating graph...")

    original_graph = nx.erdos_renyi_graph(n_nodes, p, directed=True)
    g = original_graph

    # original_graph = nx.random_geometric_graph(n_nodes, 0.20)
    # g = nx.DiGraph(original_graph)
    c = np.zeros(g.number_of_edges())
    for idx, (u,v) in enumerate(g.edges()):
        g[u][v]['idx'] = idx
        g[u][v]['weight'] = c[idx]
    
    # if nx.is_connected(original_graph):
    #     generation_succeed = True
    # else:
    #     generation_succeed = False

    print("Generating sources and destinations...")
    source_list = []
    dest_list = []
    while True:
        try:
            source, dest = np.random.choice(list(g.nodes()), size=2, replace=False)
            path = nx.shortest_path(g, source=source, target=dest)
            if len(path) < 3:
                continue
            source_list.append(source)
            dest_list.append(dest)
        except:
            continue
        if len(source_list) == n_instances:
            break

    print("Finish generating graph!")
    return g, c, source_list, dest_list

def generate_toy_graph(n_nodes=4, p=None, n_instances=300):
    assert(n_nodes==4)
    assert(n_instances==300)
    g = nx.DiGraph()
    g.add_nodes_from([0,1,2,3])
    g.add_edges_from([(0,1), (0,2), (1,2), (2,1), (1,3), (2,3)])

    g[0][1]['idx'] = 0
    g[0][2]['idx'] = 1
    g[1][2]['idx'] = 2
    g[2][1]['idx'] = 3
    g[1][3]['idx'] = 4
    g[2][3]['idx'] = 5

    c = np.zeros(g.number_of_edges())
    # source = 0
    # dest = 3
    source_list = np.array([0] * 100 + [0] * 100 + [2] * 100)
    # source_list = np.random.choice(list(g.nodes()), size=n_instances)
    dest_list = np.array([3] * 100 + [2] * 100 + [3] * 100)
    # dest_list = np.random.choice(list(g.nodes()), size=n_instances)
    return g, c, source_list, dest_list


def load_toy_data(args, kwargs, g, latency, n_instances, n_constraints=5, n_features=1, max_budget=1): # max budget is just a placeholder
    assert(n_constraints == 5)
    n_targets = g.number_of_edges()

    label1 = [0.4,0.2,0.0,0.0,0.4,0.2]
    label2 = [0.4,0.2,0.0,0.0,0.4,0.2]
    constraint_matrix = np.concatenate((np.array([[1,0,0,0,0,0], [0,0,1,0,0,0], [0,0,0,1,0,0], [0,0,0,0,1,0], [0,1,0,0,0,1]]), -np.eye(n_targets))) # box constraints with random constraints
    attacker_budgets = torch.cat((torch.Tensor([[0.0, 0.0, 0.0, 0.0, 0.3]] * n_instances), torch.zeros(n_instances, n_targets)), dim=1)

    features = torch.Tensor([[0.5] * n_features] * n_instances)
    labels = torch.Tensor([label1] * (int(n_instances/2)) + [label2] * (n_instances - int(n_instances/2)))

    # =================== dataset spliting ======================
    dataset_size = len(features)
    train_size   = int(np.floor(dataset_size * 0.8))
    test_size    = dataset_size - train_size

    entire_dataset = data_utils.TensorDataset(features, labels, attacker_budgets, torch.arange(dataset_size))
    indices = list(range(dataset_size))
    np.random.shuffle(indices)
    train_indices = indices[:train_size]
    test_indices = indices[train_size:]

    train_loader = data_utils.DataLoader(entire_dataset, batch_size=args.batch_size, **kwargs, sampler=SubsetRandomSampler(train_indices))
    test_loader  = data_utils.DataLoader(entire_dataset, batch_size=args.test_batch_size, **kwargs, sampler=SubsetRandomSampler(test_indices))

    return train_loader, test_loader, constraint_matrix


def load_data(args, kwargs, g, latency, n_instances, n_constraints, n_features=500, max_budget=1.0):
    import random
    import torch
    random.seed(SEED)
    torch.manual_seed(SEED)

    n_targets = g.number_of_edges()
    true_transform = make_fc(g.number_of_edges() + n_constraints + n_targets, n_features, num_layers=2)
    
    def bimodal_random(num_samples, num_edges):
        c = torch.zeros(num_samples, num_edges)
        for i in range(num_samples):
            for j in range(num_edges):
                tmp = random.random()
                if tmp < 0.3: # 50 % high rate
                    c[i,j] = 4 + random.random()
                elif tmp < 0.8:
                    c[i,j] = 2 + random.random()
                else: # 50 % low rate
                    c[i,j] = 0 + 0.5 * random.random()
        return c

    def random_budget(num_samples, num_constraints):
        # attacker_budget = torch.rand((num_samples, num_constraints))
        attacker_budget = torch.zeros(num_samples, num_constraints)
        for i in range(num_samples):
            for j in range(num_constraints):
                tmp = random.random()
                if tmp < 0.9:
                    attacker_budget[i,j] = 0.5 + 0.5 * random.random()
                else:
                    attacker_budget[i,j] = 0 + 0.1 * random.random()

        return attacker_budget
    
#    c_train = torch.rand(n_train, g.number_of_edges())
#    c_test = torch.rand(n_test, g.number_of_edges())

    # =========== generating constraints with budget ============
    budgets = torch.cat((max_budget * random_budget(n_instances, n_constraints), -torch.zeros(n_instances, n_targets)), dim=1)
    while True:
        constraint_matrix = np.concatenate((np.random.choice(2, size=(n_constraints, n_targets), p=[1-2.0/n_constraints,2.0/n_constraints]), -np.eye(n_targets)), axis=0) # numpy matrix
        if (np.any(np.sum(constraint_matrix[:-n_targets,:], axis=0) == 0) == False): break # make sure every entry is covered

    assert(np.any(np.sum(constraint_matrix[:-n_targets,:], axis=0) == 0) == False) # make sure every entry is covered

    # ================== generating dataset =====================
    # labels = (torch.Tensor(latency) + torch.ones(n_instances, g.number_of_edges())).float()
    labels = (torch.Tensor(latency) + bimodal_random(n_instances, g.number_of_edges())).float()
    features = true_transform(torch.cat((labels, budgets), dim=1)).detach()
    # features = true_transform(nn.functional.normalize(torch.cat((labels, budgets), dim=1))).detach()
    # features = nn.functional.normalize(torch.cat((labels, budgets), dim=1))

    # print(features.shape)
    # print(labels.shape)

    # =================== dataset spliting ======================
    dataset_size = len(features)
    train_size   = int(np.floor(dataset_size * 0.8))
    test_size    = dataset_size - train_size

    entire_dataset = data_utils.TensorDataset(features, labels, budgets, torch.arange(dataset_size))
    indices = list(range(dataset_size))
    np.random.shuffle(indices)
    train_indices = indices[:train_size]
    test_indices = indices[train_size:]

    train_loader = data_utils.DataLoader(entire_dataset, batch_size=args.batch_size, **kwargs, sampler=SubsetRandomSampler(train_indices))
    test_loader  = data_utils.DataLoader(entire_dataset, batch_size=args.test_batch_size, **kwargs, sampler=SubsetRandomSampler(test_indices))

    return train_loader, test_loader, constraint_matrix

def random_constraints(n_features, n_constraints, seed=SEED):
    np.random.seed(seed)
    max_budget = 1.0
    constraint_matrix = np.concatenate((np.random.random(size=(n_constraints, n_features)), -np.eye(n_features)), axis=0)
    budget = np.concatenate((max_budget * np.random.random(n_constraints), np.zeros(n_features)))
    return constraint_matrix, budget

class ShortestPathLoss():
    def __init__(self, n_nodes, g, c, source_list, dest_list):
        self.n_nodes = n_nodes
        self.g, self.c, self.source_list, self.dest_list = g, c, source_list, dest_list
        self.A, self.b, self.G, self.h = [], [], [], []

        assert(len(source_list) == len(dest_list)) # using the same graph g but different sources and destinations
        n_samples = len(source_list)
        for i in range(n_samples):
            tmp_A, tmp_b, tmp_G, tmp_h = make_shortest_path_matrix(self.g, self.source_list[i], self.dest_list[i])
            self.A.append(torch.Tensor(tmp_A).float())
            self.b.append(torch.Tensor(tmp_b).float())
            self.G.append(torch.Tensor(tmp_G).float())
            self.h.append(torch.Tensor(tmp_h).float())

        self.c = torch.Tensor(self.c).float()
        self.n = len(self.c)
        # self.A = torch.Tensor(self.A).float()
        # self.b = torch.Tensor(self.b).float()
        # self.G = torch.Tensor(self.G).float()
        # self.h = torch.Tensor(self.h).float()
        self.gamma = 0.1
        self.gammaQ = self.gamma * torch.eye(self.n, device="cpu")
        self.zeroQ = torch.zeros((self.n, self.n), device="cpu")

    def get_loss(self, net, features, labels, indices, eval_mode=True):
        if eval_mode:
            net.eval()

        Q = self.zeroQ
        G = self.G[indices]
        h = self.h[indices]
        A = self.A[indices]
        b = self.b[indices]

        c_pred = net(features)
        sample_number = features.shape[0]
        if c_pred.dim() == 2:
            n_train = sample_number
        else:
            n_train = 1
        c_pred = torch.Tensor.cpu(c_pred.squeeze())

        if len(A) == 0 and len(b) == 0:
            x = QPFunction(verbose=False, solver=QPSolvers.GUROBI)(Q.expand(n_train, *Q.shape), c_pred, G, h, A, b)
            # x = QPFunction(verbose=False, solver=QPSolvers.GUROBI)(Q.expand(n_train, *Q.shape), c_pred, self.G.expand(n_train, *self.G.shape), self.h.expand(n_train, *self.h.shape), self.A, self.b)
        else:
            x = QPFunction(verbose=False, solver=QPSolvers.GUROBI)(Q.expand(n_train, *Q.shape), c_pred, G, h, A, b)
            # x = QPFunction(verbose=False, solver=QPSolvers.GUROBI)(self.zeroQ.expand(n_train, *self.zeroQ.shape), c_pred, self.G.expand(n_train, *self.G.shape), self.h.expand(n_train, *self.h.shape), self.A.expand(n_train, *self.A.shape), self.b.expand(n_train, *self.b.shape))

        loss = (labels.view(sample_number, 1, labels.shape[1]).to("cpu") @ x.view(*x.shape, 1)).mean()
        net.train()
        return loss

    def relaxed_get_loss(self, net, features, labels, indices, eval_mode=True):
        if eval_mode:
            net.eval()

        Q = self.gammaQ
        G = self.G[indices]
        h = self.h[indices]
        A = self.A[indices]
        b = self.b[indices]

        c_pred = net(features)
        sample_number = features.shape[0]
        if c_pred.dim() == 2:
            n_train = sample_number
        else:
            n_train = 1
        c_pred = torch.Tensor.cpu(c_pred.squeeze())

        if len(A) == 0 and len(b) == 0:
            x = QPFunction(verbose=False, solver=QPSolvers.GUROBI)(Q.expand(n_train, *Q.shape), c_pred, G, h, A, b)
        else:
            x = QPFunction(verbose=False, solver=QPSolvers.GUROBI)(Q.expand(n_train, *Q.shape), c_pred, G, h, A, b)

        loss = (labels.view(sample_number, 1, labels.shape[1]).to("cpu") @ x.view(*x.shape, 1)).mean()
        net.train()
        return loss

    def get_two_stage_loss(self, net, features, labels, indices, eval_mode=True):
        if eval_mode:
            net.eval()

        c_pred = net(features)
        loss_fn = nn.MSELoss()
        # loss_fn = nn.BCEWithLogitsLoss() # cross entropy loss
        loss = loss_fn(c_pred, labels)
        net.train()
        return loss/len(labels)

    def get_loss_random(self, features, labels, indices):
        Q = self.zeroQ
        G = self.G[indices]
        h = self.h[indices]
        A = self.A[indices]
        b = self.b[indices]

        c_pred = torch.rand_like(labels, device="cpu")
        labels = labels.to("cpu")
        if c_pred.dim() == 2:
            n_train = features.shape[0]
        else:
            n_train = 1
        c_pred = c_pred.squeeze()

        if len(A) == 0 and len(b) == 0:
            x = QPFunction(verbose=False, solver=QPSolvers.GUROBI)(Q.expand(n_train, *Q.shape), c_pred, G, h, A, b)
        else:
            x = QPFunction(verbose=False, solver=QPSolvers.GUROBI)(Q.expand(n_train, *Q.shape), c_pred, G, h, A, b)

        loss = (labels.view(labels.shape[0], 1, labels.shape[1]) @ x.view(*x.shape, 1)).mean()
        return loss

    def get_loss_opt(self, features, labels, indices):
        Q = self.zeroQ
        G = self.G[indices]
        h = self.h[indices]
        A = self.A[indices]
        b = self.b[indices]

        labels = labels.to("cpu")
        c_pred = labels
        if c_pred.dim() == 2:
            n_train = features.shape[0]
        else:
            n_train = 1
        c_pred = c_pred.squeeze()

        if len(A) == 0 and len(b) == 0:
            x = QPFunction(verbose=False, solver=QPSolvers.GUROBI)(Q.expand(n_train, *Q.shape), c_pred, G, h, A, b)
        else:
            x = QPFunction(verbose=False, solver=QPSolvers.GUROBI)(Q.expand(n_train, *Q.shape), c_pred, G, h, A, b)

        loss = (labels.view(labels.shape[0], 1, labels.shape[1])@x.view(*x.shape, 1)).mean()
        return loss

    def get_loss_worst_case(self, net, features, labels, indices, constraint_matrix, r, eval_mode=True):
        if eval_mode:
            net.eval()

        Q = self.zeroQ
        G = self.G[indices]
        h = self.h[indices]
        A = self.A[indices]
        b = self.b[indices]

        c_pred = net(features)
        sample_number = features.shape[0]
        if c_pred.dim() == 2:
            n_train = sample_number
        else:
            n_train = 1
        c_pred = torch.Tensor.cpu(c_pred.squeeze())

        if len(A) == 0 and len(b) == 0:
            x = QPFunction(verbose=False, solver=QPSolvers.GUROBI)(Q.expand(n_train, *Q.shape), c_pred, G, h, A, b)
        else:
            x = QPFunction(verbose=False, solver=QPSolvers.GUROBI)(Q.expand(n_train, *Q.shape), c_pred, G, h, A, b)

        # print("source: {}, destination: {}, decision: {}".format(self.source_list[indices], self.dest_list[indices], x))

        # adversarial attack on the intermediate labels
        labels_modified = constrained_attack(x, labels, constraint_matrix, r)

        loss = (labels_modified.view(sample_number, 1, labels_modified.shape[1]).to("cpu") @ x.view(*x.shape, 1)).mean()
        net.train()
        return loss

    def relaxed_get_loss_worst_case(self, net, features, labels, indices, constraint_matrix, r, eval_mode=True):
        if eval_mode:
            net.eval()

        Q = self.gammaQ
        G = self.G[indices]
        h = self.h[indices]
        A = self.A[indices]
        b = self.b[indices]

        c_pred = net(features)
        sample_number = features.shape[0]
        if c_pred.dim() == 2:
            n_train = sample_number
        else:
            n_train = 1
        c_pred = torch.Tensor.cpu(c_pred.squeeze())

        if len(A) == 0 and len(b) == 0:
            x = QPFunction(verbose=False, solver=QPSolvers.GUROBI)(Q.expand(n_train, *Q.shape), c_pred, G, h, A, b)
        else:
            x = QPFunction(verbose=False, solver=QPSolvers.GUROBI)(Q.expand(n_train, *Q.shape), c_pred, G, h, A, b)

        # adversarial attack on the intermediate labels
        labels_modified = constrained_attack(x, labels, constraint_matrix, r)

        loss = (labels_modified.view(sample_number, 1, labels_modified.shape[1]).to("cpu") @ x.view(*x.shape, 1)).mean()
        net.train()
        return loss

def constrained_attack(decisions, labels, constraint_matrix, attacker_budget, relaxation=0.01): # x: decision, theta: intermediate label, C: constraint matrix, r: attacker budget
    # constraint_matrix and budget r need to be concatenated with -np.eye(n_targets) and np.zeros(n_targets)
    from gurobipy import Model, GRB, LinExpr
    batch_size = len(decisions)
    assert(len(decisions) == len(labels))

    # ======================= attacker ========================
    modified_theta = torch.zeros_like(labels)
    for i in range(batch_size):
        x, old_theta, r = decisions[i].cpu().detach().numpy(), labels[i].cpu().detach().numpy(), attacker_budget[i].cpu().detach().numpy()
        n = len(old_theta)
        m_size = len(constraint_matrix)

        model = Model("qp")
        model.params.OutputFlag=0
        model.params.TuneOutput=0

        deltas = model.addVars(n, vtype=[GRB.CONTINUOUS]*n, lb=0)
        thetas = [old_theta[j] + deltas[j] for j in range(n)]
        for j in range(m_size):
            model.addConstr(LinExpr(constraint_matrix[j], [deltas[k] for k in range(n)]) <= r[j])

        obj = sum([x[k] * thetas[k] for k in range(n)]) - relaxation * sum([thetas[j] * thetas[j] for j in range(n)])
        model.setObjective(obj, GRB.MAXIMIZE)
        model.optimize()
        for j in range(n):
            modified_theta[i][j] = old_theta[j] + deltas[j].x

    # print("modifications: {}".format(modified_theta - labels))
    # print("decision: {}".format(decisions))

    return modified_theta



