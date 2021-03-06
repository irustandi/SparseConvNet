# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

import torch
import torch.nn as nn
import torch.optim as optim
import torch.nn.functional as F
from torch.autograd import Variable
import sparseconvnet as s
import time
import os
import math


def updateStats(stats, output, target, loss):
    batchSize = output.size(0)
    stats['n'] = stats['n'] + batchSize
    stats['nll'] = stats['nll'] + loss * batchSize
    _, predictions = output.float().sort(1, True)
    correct = predictions.eq(
        target.long().view(batchSize, 1).expand_as(output))
    # Top-1 score
    stats['top1'] += correct.narrow(1, 0, 1).sum()
    # Top-5 score
    l = min(5, correct.size(1))
    stats['top5'] += correct.narrow(1, 0, l).sum()


def ClassificationTrainValidate(model, dataset, p):
    criterion = nn.CrossEntropyLoss()
    if 'n_epochs' not in p:
        p['n_epochs'] = 100
    if 'initial_lr' not in p:
        p['initial_lr'] = 1e-1
    if 'lr_decay' not in p:
        p['lr_decay'] = 4e-2
    if 'weight_decay' not in p:
        p['weight_decay'] = 1e-4
    if 'momentum' not in p:
        p['momentum'] = 0.9
    if 'check_point' not in p:
        p['check_point'] = False
    if 'use_gpu' not in p:
        p['use_gpu'] = torch.cuda.is_available()
    if p['use_gpu']:
        model.cuda()
        criterion.cuda()
    optimizer = optim.SGD(model.parameters(),
        lr=p['initial_lr'],
        momentum = p['momentum'],
        weight_decay = p['weight_decay'],
        nesterov=True)
    if p['check_point'] and os.path.isfile('epoch.pth'):
        p['epoch'] = torch.load('epoch.pth') + 1
        print('Restarting at epoch ' +
              str(p['epoch']) +
              ' from model.pth ..')
        model.load_state_dict(torch.load('model.pth'))
    else:
        p['epoch']=1
    print(p)
    print('#parameters', sum([x.nelement() for x in model.parameters()]))
    for epoch in range(p['epoch'], p['n_epochs'] + 1):
        model.train()
        stats = {'top1': 0, 'top5': 0, 'n': 0, 'nll': 0}
        for param_group in optimizer.param_groups:
            param_group['lr'] = p['initial_lr'] * \
            math.exp((1 - epoch) * p['lr_decay'])
        start = time.time()
        for batch in dataset['train']():
            if p['use_gpu']:
                batch['input']=batch['input'].cuda()
                batch['target'] = batch['target'].cuda()
            batch['input'].to_variable(requires_grad=True)
            batch['target'] = Variable(batch['target'])
            optimizer.zero_grad()
            output = model(batch['input'])
            loss = criterion(output, batch['target'])
            updateStats(stats, output.data, batch['target'].data, loss.data[0])
            loss.backward()
            optimizer.step()
        print(epoch, 'train: top1=%.2f%% top5=%.2f%% nll:%.2f time:%.1fs' %
              (100 *
               (1 -
                1.0 * stats['top1'] /
                   stats['n']), 100 *
                  (1 -
                   1.0 * stats['top5'] /
                   stats['n']), stats['nll'] /
                  stats['n'], time.time() -
                  start))

        if p['check_point']:
            torch.save(epoch, 'epoch.pth')
            torch.save(model.state_dict(),'model.pth')

        model.eval()
        s.forward_pass_multiplyAdd_count = 0
        s.forward_pass_hidden_states = 0
        stats = {'top1': 0, 'top5': 0, 'n': 0, 'nll': 0}
        start = time.time()
        for batch in dataset['val']():
            if p['use_gpu']:
                batch['input']=batch['input'].cuda()
                batch['target'] = batch['target'].cuda()
            batch['input'].to_variable()
            batch['target'] = Variable(batch['target'])
            output = model(batch['input'])
            loss = criterion(output, batch['target'])
            updateStats(stats, output.data, batch['target'].data, loss.data[0])
        print(epoch, 'test:  top1=%.2f%% top5=%.2f%% nll:%.2f time:%.1fs' %
              (100 *
               (1 -
                1.0 * stats['top1'] /
                   stats['n']), 100 *
                  (1 -
                   1.0 * stats['top5'] /
                   stats['n']), stats['nll'] /
                  stats['n'], time.time() -
                  start))
        print(
            '%.3e MultiplyAdds/sample %.3e HiddenStates/sample' %
            (s.forward_pass_multiplyAdd_count /
             stats['n'],
                s.forward_pass_hidden_states /
                stats['n']))
