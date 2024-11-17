module.exports = {
  webpack: {
    configure: (webpackConfig) => {
      // Add worker-loader
      webpackConfig.module.rules.push({
        test: /\.worker\.(js|ts)$/,
        use: {
          loader: 'worker-loader',
          options: {
            filename: '[name].[contenthash].worker.js',
          },
        },
      });

      return webpackConfig;
    },
  },
};
