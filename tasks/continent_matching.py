from collections.abc import Callable
import collections
import os
from pathlib import Path
import random

from datasets import Dataset
import torch
from torch.utils.data import DataLoader
from .task_base import TaskBase

_NO_LABEL = 'No'
_YES_LABEL = 'Yes'


class ContinentMatchingTask(TaskBase):

    def __init__(self):
        self.country_to_continent = self._get_country_continent_map()
        self.continent_to_country = collections.defaultdict(list)
        for country, continent in self.country_to_continent.items():
            self.continent_to_country[continent].append(country)
        self.countries = [c for c in self.country_to_continent]
        self.continents = [c for c in self.continent_to_country]

    def _sample_not_in_continent(self, continent):
        ret_continent = random.choice(
            [c for c in self.continents if c != continent])
        return random.choice(self.continent_to_country[ret_continent])

    def _are_same_continent(self, country1, country2):
        return (self.country_to_continent[country1] ==
                self.country_to_continent[countryt2])

    def _get_country_continent_map(self):
        ret = {}
        base_data = os.path.join(
            Path(__file__).parent, 'countries_continents.csv')
        with open(base_data) as f:
            for line in f:
                line = line.strip()
                comma_parts = line.split(',')
                continent = comma_parts[0]
                if continent not in ('Asia', 'Africa', 'North America',
                                     'South America', 'Oceania', 'Europe'):
                    continue
                country = ','.join(comma_parts[1:])
                ret[country] = continent
            return ret

    def _format_prompt(self,
                       country1: str,
                       country2: str,
                       custom_prompt_fn: Callable = None):
        if custom_prompt_fn:
            return custom_prompt_fn(country1, country2)
        return f'''Answer the following yes/no question:\n\nAre {country1} and {country2} on the same continent?\n'''

    def _sample_single_example(self,
                               target_label: bool = None,
                               custom_prompt_fn: Callable = None):
        '''
        Sample a single example.

        Args:
            target_label: if set (to either True or False), will sample an example that has this label. Otherwise will sample randomly.
            custom_prompt_fn: if set, this must be a function that accepts two countries and formats a (string) input prompt.

        Returns: a dictionary with keys 'inputs' and 'targets', both with values encoded as strings.
        '''
        # First sample country1
        country1 = random.choice(self.countries)
        continent1 = self.country_to_continent[country1]

        if target_label is None:
            # sample randomly
            country2 = random.choice(self.countries)
            continent2 = self.country_to_continent[country2]
        elif target_label:
            # sample randomly from the same continent
            country2 = random.choice(self.continent_to_country[continent1])
            continent2 = self.country_to_continent[country2]
        else:
            # sample randomly from the other continents
            continent2 = random.choice(
                [c for c in self.continents if c != continent1])
            country2 = random.choice(self.continent_to_country[continent2])

        example = {
            'inputs': self._format_prompt(country1, country2,
                                          custom_prompt_fn),
            'targets': 'Yes' if continent1 == continent2 else 'No'
        }
        print('sampled', example)
        return example

    def _encode_string(self, tokenizer, string):
        return tokenizer(string,
                         return_tensors='pt',
                         padding='max_length',
                         max_length=30).input_ids[0].tolist()

    def _encode_input_and_target(self, tokenizer, input_string, target_string):
        input_ids = tokenizer(input_string,
                              return_tensors='pt',
                              padding='max_length',
                              max_length=40).input_ids[0]
        label = tokenizer.convert_tokens_to_ids(target_string)
        output_ids = (torch.ones(input_ids.shape[0]) * -100).long().tolist()
        output_ids[-1] = label
        input_ids = input_ids.tolist()
        return input_ids, output_ids

    def _encode_alignment_examples(self, tokenizer, examples: list[dict[str,
                                                                        str]]):
        all_base_inputs = []
        all_source_inputs = []
        all_base_outputs = []
        all_source_outputs = []
        all_ctf_outputs = []
        for example in examples:
            base_input_ids, base_output_ids = self._encode_input_and_target(
                example['base_inputs'], example['base_targets'])
            source_input_ids, source_output_ids = self._encode_input_and_target(
                example['source_inputs'], example['source_targets'])
            _, ctf_output_ids = self._encode_input_and_target(
                example['base_inputs'], example['ctf_targets'])
            all_base_inputs.append(base_input_ids)
            all_base_outputs.append(base_output_ids)
            all_source_inputs.append(source_input_ids)
            all_source_outputs.append(source_input_ids)
            all_ctf_outputs.append(ctf_input_ids)
        return all_base_inputs, all_source_inputs, all_base_outputs, all_source_outputs, all_ctf_outputs

    def _encode_examples(self, tokenizer, examples: list[dict[str, str]]):
        '''
        Returns input_ids, target_ids (both lists of lists of ints)
        '''
        all_input_ids = []
        all_output_ids = []
        all_source_input_ids = []
        for example in examples:
            if 'source_inputs' in example:
                source_input_ids = self._encode_string(
                    tokenizer, example['source_inputs'])
                all_source_input_ids.append(source_input_ids)

            input_ids = tokenizer(example['inputs'],
                                  return_tensors='pt',
                                  padding='max_length',
                                  max_length=40).input_ids[0]
            label = tokenizer.convert_tokens_to_ids(example['targets'])
            output_ids = (torch.ones(input_ids.shape[0]) *
                          -100).long().tolist()
            output_ids[-1] = label
            input_ids = input_ids.tolist()
            all_input_ids.append(input_ids)
            all_output_ids.append(output_ids)

        if all_source_input_ids:
            return all_input_ids, all_source_input_ids, all_output_ids
        return all_input_ids, all_output_ids

    def output_rep_source_sampler(self, base_country1, base_country2,
                                  ctf_label_str):
        """
        A source sampler that aligns on the output. This will just sample a source example where the source target matchs ctf_target.
        """
        source_country1 = random.choice(self.countries)
        source_cont1 = self.country_to_continent[source_country1]
        if ctf_label_str == _NO_LABEL:
            source_country2 = self._sample_not_in_continent(source_cont1)
        else:
            source_country2 = random.choice(
                self.continent_to_country[source_cont1])
        return source_country1, source_country2, ctf_label_str

    def continent1_source_sampler(self, base_country1, base_country2,
                                  ctf_label_str):
        if ctf_label_str == _YES_LABEL:
            # Then we want the source cont1 = base cont2
            source_country1 = random.choice(
                self.continent_to_country[base_continent2])
            source_country2 = random.choice(self.countries)
        else:
            # Then we want source cont1 != base cont2
            source_country1 = self._sample_not_in_continent(base_continent2)
            source_country2 = random.choice(self.countries)
        source_label = self._are_same_continent(source_country1,
                                                source_country2)
        source_label = _YES_LABEL if source_label else _NO_LABEL
        return source_country1, source_country2, source_label

    def alignment_example_sampler(self, n_examples, source_sampler):
        """
        Args:
            n_examples: number of examples to sample.
            source_sampler: a function that will take in country1, country2, ctf_target and return source example (source country1 and country2).
        """
        all_examples = []
        for _ in range(n_examples):
            base_country1 = random.choice(self.countries)
            base_continent1 = self.country_to_continent[base_country1]
            base_country2 = random.choice(self.countries)
            base_continent2 = self.country_to_continent[base_country2]
            base_label_str = _YES_LABEL if base_continent1 == base_continent2 else _NO_LABEL

            intervention_id = 0
            ctf_label_str = random.choice([_YES_LABEL, _NO_LABEL])
            source_country1, source_country2, source_label_str = source_sampler(
                base_country1, base_country2, ctf_label_str)

            # Now generate the base and source inputs
            base_input_str = self._format_prompt(base_country1, base_country2)
            source_input_str = self._format_prompt(source_country1,
                                                   source_country2)
            example = {
                'inputs': base_input_str,
                'source_inputs': source_input_str,
                'targets': ctf_label_str,
                'intervention_id': intervention_id
            }
            if random.random() < 0.005:
                print(example)
            all_examples.append(example)
        return all_examples

    def prepare_dataloader(self, tokenizer, **kwargs):
        '''
        Expected kwargs:
        train_batch_size
        eval_batch_size
        task_name
        n_train
        n_eval
        '''
        eval_batch_size = kwargs['eval_batch_size']
        train_batch_size = kwargs['train_batch_size']
        task_name = kwargs['task_name']
        n_train = kwargs['n_training_examples']
        n_eval = kwargs['n_eval_examples']

        prealign_str_examples = []
        for _ in range(n_eval // 2):
            prealign_str_examples.append(self._sample_single_example(True))
            prealign_str_examples.append(self._sample_single_example(False))

        # Encode the prealign examples
        input_ids, output_ids = self._encode_examples(tokenizer,
                                                      prealign_str_examples)

        prealign_dataset = Dataset.from_dict({
            "input_ids":
            input_ids,
            "labels":
            output_ids,
            'output_only_labels': [o[-1:] for o in output_ids],
        }).with_format("torch")
        prealign_dataloader = DataLoader(prealign_dataset,
                                         batch_size=eval_batch_size)

        if 'continent_map' in task_name:
            examples = self.alignment_example_sampler(
                n_train + n_eval + n_eval, self.continent1_source_sampler)
        elif 'output_rep' in task_name:
            examples = self.alignment_example_sampler(
                n_train + n_eval + n_eval, self.output_rep_source_sampler)
        else:
            raise ValueError('Invalid continent matching task name!',
                             task_name)

        train_examples = examples[:n_train]
        dev_examples = examples[n_train:n_train + n_eval]
        test_examples = examples[n_train + n_eval:]
        train_input_ids, train_source_ids, train_output_ids = self._encode_examples(
            tokenizer, train_examples)
        dev_input_ids, dev_source_ids, dev_output_ids = self._encode_examples(
            tokenizer, dev_examples)
        test_input_ids, test_source_ids, test_output_ids = self._encode_examples(
            tokenizer, test_examples)

        train_dataset = Dataset.from_dict({
            'input_ids':
            train_input_ids,
            'labels':
            train_output_ids,
            'output_only_labels': [o[-1:] for o in train_output_ids],
            'source_input_ids':
            train_source_ids,
            'intervention_ids': [0 for _ in train_source_ids],
        }).with_format('torch')

        dev_dataset = Dataset.from_dict({
            'input_ids':
            dev_input_ids,
            'labels':
            dev_output_ids,
            'output_only_labels': [o[-1:] for o in dev_output_ids],
            'source_input_ids':
            dev_source_ids,
            'intervention_ids': [0 for _ in dev_source_ids],
        }).with_format('torch')

        test_dataset = Dataset.from_dict({
            'input_ids':
            test_input_ids,
            'labels':
            test_output_ids,
            'output_only_labels': [o[-1:] for o in test_output_ids],
            'source_input_ids':
            test_source_ids,
            'intervention_ids': [0 for _ in test_source_ids],
        }).with_format('torch')

        train_dataloader = DataLoader(train_dataset,
                                      batch_size=train_batch_size)
        dev_dataloader = DataLoader(dev_dataset, batch_size=eval_batch_size)
        test_dataloader = DataLoader(test_dataset, batch_size=eval_batch_size)

        return prealign_dataloader, train_dataloader, dev_dataloader, test_dataloader
