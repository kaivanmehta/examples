from __future__ import print_function
import argparse
import torch
import torch.nn as nn
import torch.optim as optim
import torch.nn.functional as F
import torch.multiprocessing as mp
from torch.utils.data.sampler import Sampler
from torchvision import datasets, transforms
import time

from nni.algorithms.compression.pytorch.quantization import NaiveQuantizer, QAT_Quantizer, DoReFaQuantizer, BNNQuantizer, LsqQuantizer, ObserverQuantizer

from train import train, test

# Training settings
parser = argparse.ArgumentParser(description='PyTorch MNIST Example')
parser.add_argument('--batch-size', type=int, default=64, metavar='N',
                    help='input batch size for training (default: 64)')
parser.add_argument('--test-batch-size', type=int, default=1000, metavar='N',
                    help='input batch size for testing (default: 1000)')
parser.add_argument('--epochs', type=int, default=10, metavar='N',
                    help='number of epochs to train (default: 10)')
parser.add_argument('--lr', type=float, default=0.01, metavar='LR',
                    help='learning rate (default: 0.01)')
parser.add_argument('--momentum', type=float, default=0.5, metavar='M',
                    help='SGD momentum (default: 0.5)')
parser.add_argument('--seed', type=int, default=1, metavar='S',
                    help='random seed (default: 1)')
parser.add_argument('--log-interval', type=int, default=10, metavar='N',
                    help='how many batches to wait before logging training status')
parser.add_argument('--num-processes', type=int, default=2, metavar='N',
                    help='how many training processes to use (default: 2)')
parser.add_argument('--cuda', action='store_true', default=False,
                    help='enables CUDA training')
parser.add_argument('--mps', action='store_true', default=False,
                        help='enables macOS GPU training')
parser.add_argument('--dry-run', action='store_true', default=False,
                    help='quickly check a single pass')

class Net(nn.Module):
    def __init__(self):
        super(Net, self).__init__()
        self.conv1 = nn.Conv2d(1, 10, kernel_size=5)
        self.conv2 = nn.Conv2d(10, 20, kernel_size=5)
        self.conv2_drop = nn.Dropout2d()
        self.fc1 = nn.Linear(320, 50)
        self.fc2 = nn.Linear(50, 10)

    def forward(self, x):
        x = F.relu(F.max_pool2d(self.conv1(x), 2))
        x = F.relu(F.max_pool2d((self.conv2_drop(self.conv2(x))),2))
        x = x.view(-1, 320)
        x = F.relu(self.fc1(x))
        #x = F.dropout(x, p = 0.2, training=True)
        x = self.fc2(x)
        return F.log_softmax(x, dim=1)


if __name__ == '__main__':
    args = parser.parse_args()

    use_cuda = args.cuda and torch.cuda.is_available()
    use_mps = args.mps and torch.backends.mps.is_available()
    if use_cuda:
        device = torch.device("cuda")
    elif use_mps:
        device = torch.device("mps")
    else:
        device = torch.device("cpu")

    transform=transforms.Compose([
        transforms.ToTensor(),
        transforms.Normalize((0.1307,), (0.3081,))
        ])
    dataset1 = datasets.MNIST('../data', train=True, download=True,
                       transform=transform)
    dataset2 = datasets.MNIST('../data', train=False,
                       transform=transform)
    kwargs = {'batch_size': args.batch_size,
              'shuffle': True}
    if use_cuda:
        kwargs.update({'num_workers': 1,
                       'pin_memory': True,
                      })

    torch.manual_seed(args.seed)
    mp.set_start_method('spawn', force=True)

    model = Net().to(device)
    model.share_memory() # gradients are allocated lazily, so they are not shared here
    print("model description:")
    print(model)
    
    processes = []
    start = time.time()
    train(0, args, model, device, dataset1, kwargs)
    stop = time.time()

    
    print("before pruning: entire training took: ", (stop - start)/60, "minutes!")
    
    # Once training is complete, we can test the model
    start = time.time()
    test(args, model, device, dataset2, kwargs)
    stop = time.time()
    print("before pruning: testing took: ", (stop - start)/60, "minutes!")
    print(model)
   

#     config_list = [{
#       'quant_types': ['weight'], 
#       'quant_bits': {'weight': 8}, 
#       'op_types': ['Conv2d'],
#     }]
#     NaiveQuantizer(model, config_list).compress()
    
    config_list = [{
      'quant_types': ['weight', 'input', 'output'], 
      'quant_bits': {'weight': 8, 'input': 8, 'output': 8}, 
      'op_types': ['Conv2d']
    }]

    optimizer = optim.SGD(model.parameters(), lr=args.lr, momentum=args.momentum)
    ObserverQuantizer(model, config_list).compress()
#     LsqQuantizer(model, config_list, optimizer = optimizer).compress()
#     BNNQuantizer(model, config_list, optimizer = optimizer).compress()
    
    
    print(model)
    
    processes = []
    start = time.time()
    train(0, args, model, device, dataset1, kwargs)
    stop = time.time()

    
    print("after pruning and speedup: entire training took: ", (stop - start)/60, "minutes!")
    
    # Once training is complete, we can test the model
    start = time.time()
    test(args, model, device, dataset2, kwargs)
    stop = time.time()
    print("after pruning and speed up: testing took: ", (stop - start)/60, "minutes!")
