export type TabId = 'home' | 'options' | 'try' | 'plan' | 'expert';

export const TABS: { id: TabId; n: string; label: string; hint: string }[] = [
  { id: 'home', n: '1', label: 'Your home', hint: 'How it scores' },
  { id: 'options', n: '2', label: 'Your options', hint: 'Three plans' },
  { id: 'try', n: '3', label: 'Try changes', hint: 'See what moves' },
  { id: 'plan', n: '4', label: 'Your plan', hint: 'Check & save' },
  { id: 'expert', n: '+', label: 'Expert details', hint: 'Every number' },
];
