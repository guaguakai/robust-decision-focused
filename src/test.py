import autograd.numpy as np
import torch
from torch.autograd import grad, Variable
import autograd

a = torch.FloatTensor([1, 2, 3])
b = torch.FloatTensor([3, 4, 5])

a, b = Variable(a, requires_grad=True), Variable(b, requires_grad=True)

c = a**2 + b**2
c = c.sum()

grad_b = torch.autograd.grad(c)

d = Variable(torch.Tensor(b), requires_grad=True)
e = grad_b(d)
print(e)

# grad2_b = torch.autograd.grad(grad_b)
# print(grad2_b(b))
