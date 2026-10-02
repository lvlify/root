import { createRequire } from 'node:module';

const { body } = createRequire(import.meta.url)('./context.cjs');

export default {
  id: 'root',
  server: async () => {
    const context = body();
    return {
      'experimental.chat.system.transform': async (_input, output) => {
        if (!output.system.some(text => text.includes(context))) output.system.push(context);
      },
    };
  },
};
